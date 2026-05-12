"""sentiment.source_credibility_scorer — one-time source credibility scoring.

Finds source_identifiers present in raw_mentions but absent from the
source_credibility table, collects 3-5 sample mentions per source,
calls Sonnet (source_credibility.v1) to score each, and upserts results.

This agent is designed to run once per new source, not per mention.
Existing scored sources are never re-scored unless 'rescore=true' is set.

Input params:
  scheme_key  (str, default "") — restrict to sources active for a scheme
  batch_size  (int, default 30) — new sources to score per run
  rescore     (bool, default false) — if true, re-score existing rows too
  sample_size (int, default 5) — mentions to sample per source for LLM context
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
from core.contracts import SourceCredibilityOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

_PROMPT_KEY = "sentiment_analyser.source_credibility.v1"


@register
class SourceCredibilityScorerAgent(BaseAgent):
    name = "sentiment_source_credibility_scorer"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        batch_size: int = int(ctx.params.get("batch_size", 30))
        rescore: bool = str(ctx.params.get("rescore", "false")).lower() == "true"
        sample_size: int = int(ctx.params.get("sample_size", 5))

        sources = await _fetch_unscored_sources(
            scheme_key=scheme_key,
            org_id=ctx.org_id,
            db=ctx.db,
            limit=batch_size,
            rescore=rescore,
        )

        if not sources:
            return AgentResult(
                status="success",
                data={"scored": 0, "scheme_key": scheme_key},
            )

        template = await PromptRegistry().get(_PROMPT_KEY, ctx.db)
        scored = 0
        errors = 0

        for source_identifier in sources:
            try:
                samples = await _fetch_samples(
                    source_identifier=source_identifier,
                    org_id=ctx.org_id,
                    db=ctx.db,
                    limit=sample_size,
                )
                source_handle = _derive_handle(source_identifier)

                prompt = (
                    template
                    .replace("SOURCE_IDENTIFIER", source_identifier)
                    .replace("SOURCE_HANDLE", source_handle)
                    .replace("SOURCE_SAMPLES_JSON", json.dumps(samples))
                )

                raw = await ctx.llm.complete(
                    prompt=prompt,
                    tier="standard",
                    org_id=ctx.org_id,
                    run_id=ctx.run_id,
                    db=ctx.db,
                )
                result = _parse_output(raw)

                await _upsert_credibility(
                    source_identifier=source_identifier,
                    source_handle=source_handle,
                    result=result,
                    org_id=ctx.org_id,
                    db=ctx.db,
                )
                scored += 1
            except Exception as exc:
                logger.warning(
                    "source_credibility_scorer: failed source %r — %s",
                    source_identifier, exc,
                )
                errors += 1

        logger.info(
            "source_credibility_scorer: scored=%d errors=%d scheme=%s",
            scored, errors, scheme_key or "(all)",
        )
        return AgentResult(
            status="success",
            data={
                "scored": scored,
                "errors": errors,
                "scheme_key": scheme_key,
            },
        )


# ── Handle derivation ─────────────────────────────────────────────────────────

def _derive_handle(source_identifier: str) -> str:
    """Best-effort human-readable handle from source_identifier."""
    if ":" in source_identifier:
        parts = source_identifier.split(":", 1)
        return parts[1].strip() or source_identifier
    return source_identifier


# ── JSON parsing ──────────────────────────────────────────────────────────────

def _parse_output(raw: str) -> SourceCredibilityOutput:
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
        return SourceCredibilityOutput(**data)
    except (ValidationError, TypeError):
        return SourceCredibilityOutput(
            source_type=str(data.get("source_type", "unknown")),
            estimated_reach=str(data.get("estimated_reach", "unknown")),
            editorial_standards=str(data.get("editorial_standards", "unknown")),
            known_political_lean=str(data.get("known_political_lean", "unknown")),
            credibility_weight=float(data.get("credibility_weight", 1.0)),
            reach_weight=float(data.get("reach_weight", 1.0)),
            rationale=str(data.get("rationale", ""))[:500],
            requires_human_review=bool(data.get("requires_human_review", True)),
            human_review_reason=str(data.get("human_review_reason", ""))[:300],
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_unscored_sources(
    scheme_key: str,
    org_id: str,
    db: AsyncSession,
    limit: int,
    rescore: bool,
) -> list[str]:
    if rescore:
        result = await db.execute(
            text("""
                SELECT DISTINCT source_identifier
                FROM raw_mentions
                WHERE org_id = :org_id
                  AND source_identifier <> ''
                  AND (:scheme_key = '' OR scheme_hint ? :scheme_key)
                ORDER BY source_identifier
                LIMIT :limit
            """),
            {"org_id": org_id, "scheme_key": scheme_key, "limit": limit},
        )
    else:
        result = await db.execute(
            text("""
                SELECT DISTINCT rm.source_identifier
                FROM raw_mentions rm
                WHERE rm.org_id = :org_id
                  AND rm.source_identifier <> ''
                  AND (:scheme_key = '' OR rm.scheme_hint ? :scheme_key)
                  AND NOT EXISTS (
                      SELECT 1 FROM source_credibility sc
                      WHERE sc.org_id = :org_id
                        AND sc.source_identifier = rm.source_identifier
                  )
                ORDER BY rm.source_identifier
                LIMIT :limit
            """),
            {"org_id": org_id, "scheme_key": scheme_key, "limit": limit},
        )
    return [str(row[0]) for row in result.fetchall()]


async def _fetch_samples(
    source_identifier: str,
    org_id: str,
    db: AsyncSession,
    limit: int,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT title, body, url, author, published_at
            FROM raw_mentions
            WHERE org_id = :org_id
              AND source_identifier = :src
            ORDER BY collected_at DESC
            LIMIT :limit
        """),
        {"org_id": org_id, "src": source_identifier, "limit": limit},
    )
    rows = []
    for row in result.fetchall():
        d = dict(row._mapping)
        if d.get("published_at"):
            d["published_at"] = d["published_at"].isoformat()
        # Truncate body to keep prompt cost down
        if d.get("body"):
            d["body"] = str(d["body"])[:300]
        rows.append(d)
    return rows


async def _upsert_credibility(
    source_identifier: str,
    source_handle: str,
    result: SourceCredibilityOutput,
    org_id: str,
    db: AsyncSession,
) -> None:
    await db.execute(
        text("""
            INSERT INTO source_credibility (
                id, org_id, source_identifier, source_handle,
                source_type, estimated_reach, editorial_standards,
                known_political_lean, credibility_weight, reach_weight,
                rationale, requires_human_review, human_review_reason,
                scored_by, scored_at, created_at, updated_at
            ) VALUES (
                gen_random_uuid(), :org_id, :source_identifier, :source_handle,
                :source_type, :estimated_reach, :editorial_standards,
                :known_political_lean, :credibility_weight, :reach_weight,
                :rationale, :requires_human_review, :human_review_reason,
                'llm', now(), now(), now()
            )
            ON CONFLICT (org_id, source_identifier)
            DO UPDATE SET
                source_handle        = EXCLUDED.source_handle,
                source_type          = EXCLUDED.source_type,
                estimated_reach      = EXCLUDED.estimated_reach,
                editorial_standards  = EXCLUDED.editorial_standards,
                known_political_lean = EXCLUDED.known_political_lean,
                credibility_weight   = EXCLUDED.credibility_weight,
                reach_weight         = EXCLUDED.reach_weight,
                rationale            = EXCLUDED.rationale,
                requires_human_review = EXCLUDED.requires_human_review,
                human_review_reason  = EXCLUDED.human_review_reason,
                scored_by            = 'llm',
                scored_at            = now(),
                updated_at           = now()
        """),
        {
            "org_id": org_id,
            "source_identifier": source_identifier,
            "source_handle": source_handle,
            "source_type": result.source_type,
            "estimated_reach": result.estimated_reach,
            "editorial_standards": result.editorial_standards,
            "known_political_lean": result.known_political_lean,
            "credibility_weight": result.credibility_weight,
            "reach_weight": result.reach_weight,
            "rationale": result.rationale[:2000],
            "requires_human_review": result.requires_human_review,
            "human_review_reason": result.human_review_reason[:500],
        },
    )
    await db.flush()
