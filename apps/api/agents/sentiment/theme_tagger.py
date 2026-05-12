"""sentiment.theme_tagger — Stage 3 theme classification.

Reads 'polarity_done' relevant_mentions, assigns themes from the global
theme_taxonomy using keyword pattern matching. Falls back to Haiku LLM
(theme_classifier prompt) only when:
  - pattern matching returns < 2 themes, AND
  - mention source_weight >= 0.7  (journalist / high-reach content)

Writes:
  - analyzed_mentions.themes          (JSONB array of theme_key strings)
  - analyzed_mentions.theme_confidence (JSONB dict {theme_key: confidence})
Updates relevant_mention.status → 'theme_done'.

Input params:
  scheme_key   (str, default "")
  district_key (str, default "")
  batch_size   (int, default 100)
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
from core.contracts import ThemeClassifierOutput, ThemeMatchItem
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

_PATTERN_CONFIDENCE = 0.90   # confidence assigned to pattern-matched themes
_WEIGHT_LLM_FALLBACK = 0.70  # source_weight threshold to trigger LLM fallback
_MIN_PATTERN_HITS = 2        # below this → attempt LLM fallback (if high-weight)
_PROMPT_KEY = "sentiment_analyser.theme_classifier.v1"


@register
class ThemeTaggerAgent(BaseAgent):
    name = "sentiment_theme_tagger"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        district_key: str = ctx.params.get("district_key", "")
        batch_size: int = int(ctx.params.get("batch_size", 100))

        # Load taxonomy once per run
        taxonomy = await _load_taxonomy(ctx.db)
        if not taxonomy:
            logger.warning("theme_tagger: taxonomy is empty — skipping run")
            return AgentResult(
                status="success",
                data={"processed": 0, "warning": "taxonomy_empty"},
            )

        pending = await _fetch_pending(scheme_key, ctx.org_id, ctx.db, batch_size)

        stats = {"pattern_only": 0, "llm_fallback": 0, "error": 0}
        registry = PromptRegistry()
        template: str | None = None

        for m in pending:
            try:
                body = str(m.get("body_clean") or "")
                source_weight = float(m.get("source_weight") or 1.0)

                # 1. Pattern matching
                matches = _pattern_match(body, taxonomy)

                # 2. LLM fallback for high-weight, low-match mentions
                method = "pattern"
                if len(matches) < _MIN_PATTERN_HITS and source_weight >= _WEIGHT_LLM_FALLBACK:
                    if template is None:
                        template = await registry.get(_PROMPT_KEY, ctx.db)
                    llm_matches = await _llm_classify(
                        mention=m,
                        taxonomy=taxonomy,
                        scheme_key=scheme_key,
                        district_key=district_key,
                        template=template,
                        ctx=ctx,
                    )
                    if llm_matches:
                        matches = _merge_matches(matches, llm_matches)
                        method = "llm"

                themes = [t.theme_key for t in matches]
                confidence = {t.theme_key: t.confidence for t in matches}

                await _update_themes(
                    relevant_id=str(m["id"]),
                    org_id=ctx.org_id,
                    themes=themes,
                    confidence=confidence,
                    db=ctx.db,
                )
                stats["llm_fallback" if method == "llm" else "pattern_only"] += 1

            except Exception as exc:
                logger.warning(
                    "theme_tagger: failed mention %s — %s", m.get("id"), exc
                )
                stats["error"] += 1

        total = stats["pattern_only"] + stats["llm_fallback"]
        logger.info(
            "theme_tagger: processed=%d pattern=%d llm=%d err=%d scheme=%s",
            total, stats["pattern_only"], stats["llm_fallback"],
            stats["error"], scheme_key or "(all)",
        )
        return AgentResult(
            status="success",
            data={"processed": total, **stats, "scheme_key": scheme_key},
        )


# ── Pattern matching ──────────────────────────────────────────────────────────

def _pattern_match(
    body: str,
    taxonomy: list[dict[str, Any]],
) -> list[ThemeMatchItem]:
    lower = body.lower()
    hits: list[ThemeMatchItem] = []
    for entry in taxonomy:
        patterns: list[str] = entry.get("patterns_en") or []
        matched = any(p.lower() in lower for p in patterns if len(p) > 2)
        if matched:
            hits.append(ThemeMatchItem(
                theme_key=str(entry["theme_key"]),
                confidence=_PATTERN_CONFIDENCE,
                evidence_quote="",
            ))
    return hits


def _merge_matches(
    pattern_hits: list[ThemeMatchItem],
    llm_hits: list[ThemeMatchItem],
) -> list[ThemeMatchItem]:
    seen = {t.theme_key for t in pattern_hits}
    merged = list(pattern_hits)
    for t in llm_hits:
        if t.theme_key not in seen:
            merged.append(t)
            seen.add(t.theme_key)
    return merged[:5]  # cap at 5 per spec


# ── LLM fallback ──────────────────────────────────────────────────────────────

async def _llm_classify(
    mention: dict[str, Any],
    taxonomy: list[dict[str, Any]],
    scheme_key: str,
    district_key: str,
    template: str,
    ctx: AgentContext,
) -> list[ThemeMatchItem]:
    taxonomy_json = json.dumps(
        [
            {
                "theme_key": e["theme_key"],
                "description": e.get("description", ""),
                "examples": (e.get("patterns_en") or [])[:5],
            }
            for e in taxonomy
        ]
    )
    body = str(mention.get("body_clean") or "")[:2000]
    lang = str(mention.get("language") or "unknown")

    prompt = (
        template
        .replace("THEME_TAXONOMY_JSON", taxonomy_json)
        .replace("MENTION_TEXT", body)
        .replace("SCHEME_NAME", scheme_key or "unknown")
        .replace("DISTRICT_NAME", district_key or "unknown")
        .replace("DETECTED_LANGUAGE", lang)
    )

    raw = await ctx.llm.complete(
        prompt=prompt, tier="fast", org_id=ctx.org_id, run_id=ctx.run_id, db=ctx.db
    )
    return _parse_theme_output(raw)


def _parse_theme_output(raw: str) -> list[ThemeMatchItem]:
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
        result = ThemeClassifierOutput(**data)
    except (ValidationError, TypeError):
        result = ThemeClassifierOutput(
            matched_themes=[
                ThemeMatchItem(**item)
                for item in (data.get("matched_themes") or [])
                if isinstance(item, dict)
            ]
        )
    return [t for t in result.matched_themes if t.confidence >= 0.6]


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _load_taxonomy(db: AsyncSession) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT theme_key, label_en, label_ta, description,
                   patterns_en, patterns_ta
            FROM theme_taxonomy
            WHERE is_active = true
            ORDER BY theme_key
        """)
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def _fetch_pending(
    scheme_key: str,
    org_id: str,
    db: AsyncSession,
    limit: int,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT id, org_id, matched_scheme, matched_district,
                   body_clean, language, source_weight
            FROM relevant_mentions
            WHERE org_id = :org_id
              AND status = 'polarity_done'
              AND (:scheme_key = '' OR matched_scheme = :scheme_key)
            ORDER BY created_at ASC
            LIMIT :limit
        """),
        {"org_id": org_id, "scheme_key": scheme_key, "limit": limit},
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def _update_themes(
    relevant_id: str,
    org_id: str,
    themes: list[str],
    confidence: dict[str, float],
    db: AsyncSession,
) -> None:
    await db.execute(
        text("""
            UPDATE analyzed_mentions
            SET themes = CAST(:themes AS jsonb),
                theme_confidence = CAST(:confidence AS jsonb)
            WHERE relevant_mention_id = :relevant_id
              AND org_id = :org_id
        """),
        {
            "themes": json.dumps(themes),
            "confidence": json.dumps(confidence),
            "relevant_id": relevant_id,
            "org_id": org_id,
        },
    )
    await db.execute(
        text(
            "UPDATE relevant_mentions SET status = 'theme_done' WHERE id = :id"
        ),
        {"id": relevant_id},
    )
    await db.flush()
