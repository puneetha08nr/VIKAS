"""sentiment.polarity_classifier — Stage 3 polarity analysis.

Reads 'pending_analysis' relevant_mentions, classifies each using a three-tier
cascade, writes an analyzed_mentions row, updates relevant_mention status.

Cascade order:
  1. VADER fast-path  — lang='en' AND vader_confidence >= vader_threshold
                        (no LLM; ~$0)
  2. English batch    — ≥BATCH_MIN short (< BATCH_CHAR_LIMIT) en mentions
                        (Haiku; ~70% cheaper than per-item)
  3. English individual — remaining lang='en' mentions
                        (Haiku)
  4. Tamil / mixed    — lang IN ('ta', 'mixed', 'unknown')
                        (Sonnet — handles sarcasm, regional idioms)

Input params:
  scheme_key       (str, default "")
  district_key     (str, default "")
  batch_size       (int, default 50) — relevant_mentions to fetch per run
  vader_threshold  (float, default 0.85) — VADER confidence above which LLM skipped

Output: analyzed_mentions rows (status='polarity_done' on relevant_mention).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import BatchPolarityItem, BatchPolarityOutput, PolarityOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

_BATCH_MIN = 5            # minimum mentions to trigger batch path
_BATCH_CHAR_LIMIT = 500   # body_clean length below which batch-eligible
_BATCH_MAX = 20           # max items per batch call (prompt spec limit)

_PROMPT_EN = "sentiment_analyser.polarity_classifier_en.v1"
_PROMPT_TA = "sentiment_analyser.polarity_classifier_ta.v1"
_PROMPT_BATCH = "sentiment_analyser.polarity_batch.v1"


@register
class PolarityClassifierAgent(BaseAgent):
    name = "sentiment_polarity_classifier"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        district_key: str = ctx.params.get("district_key", "")
        batch_size: int = int(ctx.params.get("batch_size", 50))
        vader_threshold: float = float(ctx.params.get("vader_threshold", 0.85))

        pending = await _fetch_pending(scheme_key, ctx.org_id, ctx.db, batch_size)
        if not pending:
            return AgentResult(
                status="success",
                data={"processed": 0, "scheme_key": scheme_key},
            )

        registry = PromptRegistry()

        # Partition mentions
        vader_pass: list[dict[str, Any]] = []
        en_long: list[dict[str, Any]] = []
        en_short: list[dict[str, Any]] = []
        ta_mixed: list[dict[str, Any]] = []

        for m in pending:
            lang = str(m.get("language") or "unknown")
            vc = float(m.get("vader_confidence") or 0.0)
            body = str(m.get("body_clean") or "")
            if lang == "en" and vc >= vader_threshold:
                vader_pass.append(m)
            elif lang == "en" and len(body) < _BATCH_CHAR_LIMIT:
                en_short.append(m)
            elif lang == "en":
                en_long.append(m)
            else:
                ta_mixed.append(m)

        stats: dict[str, int] = {
            "vader": 0, "haiku_en": 0, "haiku_batch": 0, "sonnet_ta": 0, "error": 0,
        }

        # 1. VADER fast-path
        for m in vader_pass:
            try:
                await _write_vader(m, ctx.org_id, ctx.db)
                stats["vader"] += 1
            except Exception as exc:
                logger.warning("polarity_classifier: vader write failed %s — %s", m["id"], exc)
                stats["error"] += 1

        # 2. English batch (when ≥ BATCH_MIN short mentions available)
        if len(en_short) >= _BATCH_MIN:
            template_batch = await registry.get(_PROMPT_BATCH, ctx.db)
            ph_batch = _prompt_hash(template_batch)
            for chunk_start in range(0, len(en_short), _BATCH_MAX):
                chunk = en_short[chunk_start: chunk_start + _BATCH_MAX]
                try:
                    results = await _classify_batch(
                        mentions=chunk,
                        scheme_key=scheme_key,
                        district_key=district_key,
                        template=template_batch,
                        prompt_hash=ph_batch,
                        org_id=ctx.org_id,
                        db=ctx.db,
                        ctx=ctx,
                    )
                    stats["haiku_batch"] += results
                except Exception as exc:
                    logger.warning("polarity_classifier: batch chunk failed — %s", exc)
                    en_long.extend(chunk)  # fall back to per-item
        else:
            en_long.extend(en_short)

        # 3. English individual
        if en_long:
            template_en = await registry.get(_PROMPT_EN, ctx.db)
            ph_en = _prompt_hash(template_en)
            for m in en_long:
                try:
                    await _classify_individual(
                        mention=m,
                        lang="en",
                        scheme_key=scheme_key,
                        district_key=district_key,
                        template=template_en,
                        prompt_hash=ph_en,
                        org_id=ctx.org_id,
                        db=ctx.db,
                        ctx=ctx,
                        tier="fast",
                        method="haiku_en",
                    )
                    stats["haiku_en"] += 1
                except Exception as exc:
                    logger.warning(
                        "polarity_classifier: en individual failed %s — %s", m["id"], exc
                    )
                    stats["error"] += 1

        # 4. Tamil / mixed
        if ta_mixed:
            template_ta = await registry.get(_PROMPT_TA, ctx.db)
            ph_ta = _prompt_hash(template_ta)
            for m in ta_mixed:
                try:
                    await _classify_individual(
                        mention=m,
                        lang=str(m.get("language") or "unknown"),
                        scheme_key=scheme_key,
                        district_key=district_key,
                        template=template_ta,
                        prompt_hash=ph_ta,
                        org_id=ctx.org_id,
                        db=ctx.db,
                        ctx=ctx,
                        tier="standard",
                        method="sonnet_ta",
                    )
                    stats["sonnet_ta"] += 1
                except Exception as exc:
                    logger.warning(
                        "polarity_classifier: ta individual failed %s — %s", m["id"], exc
                    )
                    stats["error"] += 1

        total = sum(v for k, v in stats.items() if k != "error")
        logger.info(
            "polarity_classifier: processed=%d vader=%d batch=%d en=%d ta=%d err=%d scheme=%s",
            total, stats["vader"], stats["haiku_batch"],
            stats["haiku_en"], stats["sonnet_ta"], stats["error"],
            scheme_key or "(all)",
        )
        return AgentResult(
            status="success",
            data={"processed": total, **stats, "scheme_key": scheme_key},
        )


# ── VADER fast-path ───────────────────────────────────────────────────────────

async def _write_vader(m: dict[str, Any], org_id: str, db: AsyncSession) -> None:
    vs = float(m.get("vader_score") or 0.0)
    vc = float(m.get("vader_confidence") or 0.0)
    if vs > 0.05:
        polarity = "positive"
    elif vs < -0.05:
        polarity = "negative"
    else:
        polarity = "neutral"

    await _insert_analyzed(
        relevant_id=str(m["id"]),
        matched_scheme=str(m.get("matched_scheme") or ""),
        matched_district=str(m.get("matched_district") or ""),
        polarity=polarity,
        polarity_score=vs,
        polarity_confidence=vc,
        polarity_method="vader",
        contains_sarcasm=False,
        is_about_scheme=True,
        prompt_hash="",
        org_id=org_id,
        db=db,
    )


# ── Individual LLM classification ────────────────────────────────────────────

async def _classify_individual(
    mention: dict[str, Any],
    lang: str,
    scheme_key: str,
    district_key: str,
    template: str,
    prompt_hash: str,
    org_id: str,
    db: AsyncSession,
    ctx: AgentContext,
    tier: str,
    method: str,
) -> None:
    body = str(mention.get("body_clean") or "")[:2000]
    source = str(mention.get("source") or "unknown")

    prompt = (
        template
        .replace("SCHEME_NAME", scheme_key or "unknown")
        .replace("DISTRICT_NAME", district_key or "unknown")
        .replace("SOURCE_TYPE", source)
        .replace("DETECTED_LANGUAGE", lang)
        .replace("MENTION_TEXT", body)
    )

    raw = await ctx.llm.complete(
        prompt=prompt, tier=tier, org_id=ctx.org_id, run_id=ctx.run_id, db=ctx.db
    )
    result = _parse_polarity(raw)

    await _insert_analyzed(
        relevant_id=str(mention["id"]),
        matched_scheme=str(mention.get("matched_scheme") or ""),
        matched_district=str(mention.get("matched_district") or ""),
        polarity=result.polarity,
        polarity_score=result.polarity_score,
        polarity_confidence=result.confidence,
        polarity_method=method,
        contains_sarcasm=result.contains_sarcasm,
        is_about_scheme=result.is_about_scheme,
        prompt_hash=prompt_hash,
        org_id=org_id,
        db=db,
    )


# ── Batch LLM classification ──────────────────────────────────────────────────

async def _classify_batch(
    mentions: list[dict[str, Any]],
    scheme_key: str,
    district_key: str,
    template: str,
    prompt_hash: str,
    org_id: str,
    db: AsyncSession,
    ctx: AgentContext,
) -> int:
    items_json = json.dumps(
        [{"id": str(m["id"]), "text": str(m.get("body_clean") or "")[:500]}
         for m in mentions]
    )
    prompt = (
        template
        .replace("SCHEME_NAME", scheme_key or "unknown")
        .replace("DISTRICT_NAME", district_key or "unknown")
        .replace("MENTION_BATCH_JSON", items_json)
    )

    raw = await ctx.llm.complete(
        prompt=prompt, tier="fast", org_id=ctx.org_id, run_id=ctx.run_id, db=ctx.db
    )
    batch_result = _parse_batch(raw)

    id_to_mention = {str(m["id"]): m for m in mentions}
    written = 0
    for item in batch_result.items:
        mention = id_to_mention.get(item.id)
        if not mention:
            continue
        await _insert_analyzed(
            relevant_id=item.id,
            matched_scheme=str(mention.get("matched_scheme") or ""),
            matched_district=str(mention.get("matched_district") or ""),
            polarity=item.polarity,
            polarity_score=item.polarity_score,
            polarity_confidence=item.confidence,
            polarity_method="haiku_batch",
            contains_sarcasm=False,
            is_about_scheme=item.is_about_scheme,
            prompt_hash=prompt_hash,
            org_id=org_id,
            db=db,
        )
        written += 1
    return written


# ── JSON parsing ──────────────────────────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    return re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()


def _parse_polarity(raw: str) -> PolarityOutput:
    cleaned = _strip_fences(raw)
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
        return PolarityOutput(**data)
    except (ValidationError, TypeError):
        return PolarityOutput(
            polarity=data.get("polarity", "neutral"),
            polarity_score=float(data.get("polarity_score", 0.0)),
            confidence=float(data.get("confidence", 0.5)),
            reasoning=str(data.get("reasoning", ""))[:200],
            contains_sarcasm=bool(data.get("contains_sarcasm", False)),
            is_about_scheme=bool(data.get("is_about_scheme", True)),
        )


def _parse_batch(raw: str) -> BatchPolarityOutput:
    cleaned = _strip_fences(raw)
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    items: list[dict[str, Any]] = []
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            items = parsed
        elif isinstance(parsed, dict) and "items" in parsed:
            items = parsed["items"]
    except Exception:
        m = re.search(r"\[.*\]", cleaned, re.DOTALL)
        if m:
            try:
                items = json.loads(m.group())
            except Exception:
                pass
    validated: list[BatchPolarityItem] = []
    for item in items:
        try:
            validated.append(BatchPolarityItem(
                id=str(item.get("id", "")),
                polarity=item.get("polarity", "neutral"),
                polarity_score=float(item.get("polarity_score", 0.0)),
                confidence=float(item.get("confidence", 0.5)),
                is_about_scheme=bool(item.get("is_about_scheme", True)),
            ))
        except (ValidationError, TypeError, ValueError):
            continue
    return BatchPolarityOutput(items=validated)


def _prompt_hash(template: str) -> str:
    return hashlib.sha256(template.encode()).hexdigest()[:16]


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_pending(
    scheme_key: str,
    org_id: str,
    db: AsyncSession,
    limit: int,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT id, org_id, source, matched_scheme, matched_district,
                   body_clean, language, vader_score, vader_confidence
            FROM relevant_mentions
            WHERE org_id = :org_id
              AND status = 'pending_analysis'
              AND (:scheme_key = '' OR matched_scheme = :scheme_key)
            ORDER BY created_at ASC
            LIMIT :limit
        """),
        {"org_id": org_id, "scheme_key": scheme_key, "limit": limit},
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def _insert_analyzed(
    relevant_id: str,
    matched_scheme: str,
    matched_district: str,
    polarity: str,
    polarity_score: float,
    polarity_confidence: float,
    polarity_method: str,
    contains_sarcasm: bool,
    is_about_scheme: bool,
    prompt_hash: str,
    org_id: str,
    db: AsyncSession,
) -> None:
    await db.execute(
        text("""
            INSERT INTO analyzed_mentions (
                id, org_id, relevant_mention_id,
                matched_scheme, matched_district,
                polarity, polarity_score, polarity_confidence, polarity_method,
                contains_sarcasm, is_about_scheme,
                themes, theme_confidence, entities,
                prompt_hash, analyzed_at, created_at
            ) VALUES (
                gen_random_uuid(), :org_id, :relevant_id,
                :matched_scheme, :matched_district,
                :polarity, :polarity_score, :polarity_confidence, :polarity_method,
                :contains_sarcasm, :is_about_scheme,
                '[]'::jsonb, '{}'::jsonb, '{}'::jsonb,
                :prompt_hash, now(), now()
            )
            ON CONFLICT DO NOTHING
        """),
        {
            "org_id": org_id,
            "relevant_id": relevant_id,
            "matched_scheme": matched_scheme,
            "matched_district": matched_district,
            "polarity": polarity,
            "polarity_score": polarity_score,
            "polarity_confidence": polarity_confidence,
            "polarity_method": polarity_method,
            "contains_sarcasm": contains_sarcasm,
            "is_about_scheme": is_about_scheme,
            "prompt_hash": prompt_hash,
        },
    )
    await db.execute(
        text(
            "UPDATE relevant_mentions SET status = 'polarity_done' WHERE id = :id"
        ),
        {"id": relevant_id},
    )
    await db.flush()
