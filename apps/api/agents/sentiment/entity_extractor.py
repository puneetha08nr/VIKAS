"""sentiment.entity_extractor — Stage 3 entity and claim extraction.

Reads 'theme_done' relevant_mentions, extracts structured entities and
verifiable claims for mentions with source_weight >= SOURCE_WEIGHT_THRESHOLD.
Low-weight mentions are passed through without LLM (sets status → 'analyzed').

Writes to analyzed_mentions.entities (JSONB dict with schemes_mentioned,
districts_mentioned, persons_mentioned, factual_claims, quoted_statements).

Updates relevant_mention.status → 'analyzed' for all processed mentions.

Input params:
  scheme_key         (str, default "")
  district_key       (str, default "")
  batch_size         (int, default 100)
  source_weight_min  (float, default 0.7) — below this, skip LLM
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import EntityExtractorOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

_PROMPT_KEY = "sentiment_analyser.entity_extractor.v1"


@register
class EntityExtractorAgent(BaseAgent):
    name = "sentiment_entity_extractor"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        batch_size: int = int(ctx.params.get("batch_size", 100))
        source_weight_min: float = float(ctx.params.get("source_weight_min", 0.7))

        pending = await _fetch_pending(scheme_key, ctx.org_id, ctx.db, batch_size)

        stats = {"extracted": 0, "skipped_low_weight": 0, "error": 0}
        registry = PromptRegistry()
        template: str | None = None

        for m in pending:
            try:
                source_weight = float(m.get("source_weight") or 1.0)

                if source_weight >= source_weight_min:
                    if template is None:
                        template = await registry.get(_PROMPT_KEY, ctx.db)
                    entities = await _extract_entities(
                        mention=m,
                        template=template,
                        ctx=ctx,
                    )
                    await _update_entities(
                        relevant_id=str(m["id"]),
                        org_id=ctx.org_id,
                        entities=entities,
                        db=ctx.db,
                    )
                    stats["extracted"] += 1
                else:
                    await _set_analyzed(str(m["id"]), ctx.db)
                    stats["skipped_low_weight"] += 1

            except Exception as exc:
                logger.warning(
                    "entity_extractor: failed mention %s — %s", m.get("id"), exc
                )
                stats["error"] += 1

        total = stats["extracted"] + stats["skipped_low_weight"]
        logger.info(
            "entity_extractor: processed=%d extracted=%d skipped=%d err=%d scheme=%s",
            total, stats["extracted"], stats["skipped_low_weight"],
            stats["error"], scheme_key or "(all)",
        )
        return AgentResult(
            status="success",
            data={"processed": total, **stats, "scheme_key": scheme_key},
        )


# ── LLM extraction ────────────────────────────────────────────────────────────

async def _extract_entities(
    mention: dict[str, Any],
    template: str,
    ctx: AgentContext,
) -> EntityExtractorOutput:
    body = str(mention.get("body_clean") or "")[:2000]
    source = str(mention.get("source") or "unknown")
    lang = str(mention.get("language") or "unknown")

    prompt = (
        template
        .replace("MENTION_TEXT", body)
        .replace("SOURCE_TYPE", source)
        .replace("DETECTED_LANGUAGE", lang)
    )

    raw = await ctx.llm.complete(
        prompt=prompt, tier="fast", org_id=ctx.org_id, run_id=ctx.run_id, db=ctx.db
    )
    return _parse_entity_output(raw)


def _parse_entity_output(raw: str) -> EntityExtractorOutput:
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    data: dict[str, Any] = {}
    try:
        data = json.loads(cleaned)
    except Exception:
        m = re.search(r"\{.*?\}", cleaned, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group())
            except Exception:
                pass
    try:
        return EntityExtractorOutput(**data)
    except (ValidationError, TypeError):
        return EntityExtractorOutput(
            schemes_mentioned=data.get("schemes_mentioned") or [],
            districts_mentioned=data.get("districts_mentioned") or [],
            persons_mentioned=data.get("persons_mentioned") or [],
            factual_claims=data.get("factual_claims") or [],
            quoted_statements=data.get("quoted_statements") or [],
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_pending(
    scheme_key: str,
    org_id: str,
    db: AsyncSession,
    limit: int,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT id, org_id, matched_scheme, matched_district,
                   body_clean, language, source, source_weight
            FROM relevant_mentions
            WHERE org_id = :org_id
              AND status = 'theme_done'
              AND (:scheme_key = '' OR matched_scheme = :scheme_key)
            ORDER BY source_weight DESC, created_at ASC
            LIMIT :limit
        """),
        {"org_id": org_id, "scheme_key": scheme_key, "limit": limit},
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def _update_entities(
    relevant_id: str,
    org_id: str,
    entities: EntityExtractorOutput,
    db: AsyncSession,
) -> None:
    await db.execute(
        text("""
            UPDATE analyzed_mentions
            SET entities = CAST(:entities AS jsonb)
            WHERE relevant_mention_id = :relevant_id
              AND org_id = :org_id
        """),
        {
            "entities": json.dumps(entities.model_dump()),
            "relevant_id": relevant_id,
            "org_id": org_id,
        },
    )
    await _set_analyzed(relevant_id, db)


async def _set_analyzed(mention_id: str, db: AsyncSession) -> None:
    await db.execute(
        text(
            "UPDATE relevant_mentions SET status = 'analyzed' WHERE id = :id"
        ),
        {"id": mention_id},
    )
    await db.flush()
