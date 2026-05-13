"""sentiment.spike_detector — Stage 4 spike analysis.

Reads sentiment_signals rows where spike_detected=True and spike_analysis
is still empty ('{}'), calls Sonnet (spike_analyzer.v1) to produce a
human-readable situation summary, and writes the result back into
sentiment_signals.spike_analysis.

The spike_detected flag is set by the aggregator (Prompt 7). This agent
provides the reasoning layer on top of that flag — never re-evaluates
whether a spike occurred.

Input params:
  scheme_key    (str, default "") — restrict to one scheme; "" = all
  district_key  (str, default "") — restrict to one district; "" = all
  batch_size    (int, default 20)
  lookback_days (int, default 7) — days of baseline stats to include in prompt
  top_mentions  (int, default 25) — top negative mentions to feed the LLM
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import SpikeAnalyzerOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

_PROMPT_KEY = "sentiment_analyser.spike_analyzer.v1"


@register
class SpikeDetectorAgent(BaseAgent):
    name = "sentiment_spike_detector"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        district_key: str = ctx.params.get("district_key", "")
        batch_size: int = int(ctx.params.get("batch_size", 20))
        lookback_days: int = int(ctx.params.get("lookback_days", 7))
        top_mentions: int = int(ctx.params.get("top_mentions", 25))

        spikes = await _fetch_unanalyzed_spikes(
            scheme_key=scheme_key,
            district_key=district_key,
            org_id=ctx.org_id,
            db=ctx.db,
            limit=batch_size,
        )

        if not spikes:
            return AgentResult(
                status="success",
                data={"analyzed": 0, "scheme_key": scheme_key},
            )

        template = await PromptRegistry().get(_PROMPT_KEY, ctx.db)
        analyzed = 0
        errors = 0

        for spike in spikes:
            try:
                baseline = await _fetch_baseline_stats(
                    scheme_key=str(spike["scheme_key"]),
                    district_key=str(spike["district_key"]),
                    before_date=spike["signal_date"],
                    days=lookback_days,
                    org_id=ctx.org_id,
                    db=ctx.db,
                )
                mentions = await _fetch_top_mentions(
                    scheme_key=str(spike["scheme_key"]),
                    district_key=str(spike["district_key"]),
                    signal_date=spike["signal_date"],
                    window_hours=int(spike.get("window_hours") or 24),
                    org_id=ctx.org_id,
                    db=ctx.db,
                    limit=top_mentions,
                )

                prompt = _build_prompt(
                    template=template,
                    spike=spike,
                    baseline=baseline,
                    mentions=mentions,
                )

                raw = await ctx.llm.complete(
                    prompt=prompt,
                    tier="standard",
                    org_id=ctx.org_id,
                    run_id=ctx.run_id,
                    db=ctx.db,
                )
                result = _parse_output(raw)

                await _write_analysis(
                    signal_id=str(spike["id"]),
                    result=result,
                    db=ctx.db,
                )
                analyzed += 1
            except Exception as exc:
                logger.warning(
                    "spike_detector: failed signal %s — %s", spike.get("id"), exc
                )
                errors += 1

        logger.info(
            "spike_detector: analyzed=%d errors=%d scheme=%s",
            analyzed, errors, scheme_key or "(all)",
        )
        return AgentResult(
            status="success",
            data={
                "analyzed": analyzed,
                "errors": errors,
                "scheme_key": scheme_key,
                "district_key": district_key,
            },
        )


# ── Prompt construction ───────────────────────────────────────────────────────

def _build_prompt(
    template: str,
    spike: dict[str, Any],
    baseline: dict[str, Any],
    mentions: list[dict[str, Any]],
) -> str:
    signal_date = spike["signal_date"]
    if isinstance(signal_date, date):
        window_start = datetime(
            signal_date.year, signal_date.month, signal_date.day, tzinfo=UTC
        ).isoformat()
        window_end = (
            datetime(signal_date.year, signal_date.month, signal_date.day, tzinfo=UTC)
            + timedelta(hours=int(spike.get("window_hours") or 24))
        ).isoformat()
    else:
        window_start = str(signal_date)
        window_end = str(signal_date)

    current_stats = json.dumps({
        "mention_count": spike.get("mention_count", 0),
        "positive_count": spike.get("positive_count", 0),
        "negative_count": spike.get("negative_count", 0),
        "neutral_count": spike.get("neutral_count", 0),
        "mixed_count": spike.get("mixed_count", 0),
        "avg_polarity_score": spike.get("avg_polarity_score"),
        "dominant_polarity": spike.get("dominant_polarity", "neutral"),
    })

    return (
        template
        .replace("SCHEME_NAME", str(spike.get("scheme_key") or "unknown"))
        .replace("DISTRICT_NAME", str(spike.get("district_key") or "unknown"))
        .replace("WINDOW_START", window_start)
        .replace("WINDOW_END", window_end)
        .replace("BASELINE_STATS", json.dumps(baseline))
        .replace("CURRENT_STATS", current_stats)
        .replace("SPIKE_MENTIONS_JSON", json.dumps(mentions))
    )


# ── JSON parsing ──────────────────────────────────────────────────────────────

def _parse_output(raw: str) -> SpikeAnalyzerOutput:
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
        return SpikeAnalyzerOutput(**data)
    except (ValidationError, TypeError):
        return SpikeAnalyzerOutput(
            situation_summary=str(data.get("situation_summary", ""))[:500],
            primary_drivers=data.get("primary_drivers") or [],
            is_organic_or_amplified=str(data.get("is_organic_or_amplified", "uncertain")),
            amplification_signals=data.get("amplification_signals") or [],
            recommended_response_type=str(
                data.get("recommended_response_type", "monitor_only")
            ),
            urgency=str(data.get("urgency", "low")),
            rationale_for_urgency=str(data.get("rationale_for_urgency", ""))[:300],
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_unanalyzed_spikes(
    scheme_key: str,
    district_key: str,
    org_id: str,
    db: AsyncSession,
    limit: int,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT id, scheme_key, district_key, signal_date, window_hours,
                   mention_count, positive_count, negative_count,
                   neutral_count, mixed_count,
                   avg_polarity_score, dominant_polarity
            FROM sentiment_signals
            WHERE org_id = :org_id
              AND spike_detected = true
              AND (spike_analysis = '{}'::jsonb OR spike_analysis IS NULL)
              AND (:scheme_key = '' OR scheme_key = :scheme_key)
              AND (:district_key = '' OR district_key = :district_key)
            ORDER BY signal_date DESC
            LIMIT :limit
        """),
        {
            "org_id": org_id,
            "scheme_key": scheme_key,
            "district_key": district_key,
            "limit": limit,
        },
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def _fetch_baseline_stats(
    scheme_key: str,
    district_key: str,
    before_date: date,
    days: int,
    org_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    result = await db.execute(
        text("""
            SELECT
                AVG(mention_count)            AS avg_mentions_per_day,
                AVG(
                    CASE WHEN mention_count > 0
                         THEN negative_count::float / mention_count * 100
                         ELSE 0 END
                )                             AS avg_negative_pct,
                AVG(weighted_avg_polarity_score) AS avg_weighted_polarity
            FROM sentiment_signals
            WHERE org_id = :org_id
              AND scheme_key = :scheme_key
              AND district_key = :district_key
              AND signal_date >= :start_date
              AND signal_date < :before_date
              AND window_hours = 24
        """),
        {
            "org_id": org_id,
            "scheme_key": scheme_key,
            "district_key": district_key,
            "start_date": before_date - timedelta(days=days),
            "before_date": before_date,
        },
    )
    row = result.fetchone()
    if row:
        return {
            "avg_mentions_per_day": round(float(row[0] or 0), 1),
            "avg_negative_pct": round(float(row[1] or 0), 1),
            "avg_weighted_polarity": round(float(row[2] or 0), 4),
        }
    return {"avg_mentions_per_day": 0, "avg_negative_pct": 0, "avg_weighted_polarity": 0.0}


async def _fetch_top_mentions(
    scheme_key: str,
    district_key: str,
    signal_date: date,
    window_hours: int,
    org_id: str,
    db: AsyncSession,
    limit: int,
) -> list[dict[str, Any]]:
    window_start = datetime(
        signal_date.year, signal_date.month, signal_date.day, tzinfo=UTC
    )
    window_end = window_start + timedelta(hours=window_hours)
    result = await db.execute(
        text("""
            SELECT am.id, rm.body_clean AS text, rm.source,
                   am.polarity, rm.source_weight, rm.published_at
            FROM analyzed_mentions am
            JOIN relevant_mentions rm ON rm.id = am.relevant_mention_id
            WHERE am.org_id = :org_id
              AND am.matched_scheme = :scheme_key
              AND am.matched_district = :district_key
              AND am.polarity = 'negative'
              AND rm.created_at >= :start
              AND rm.created_at < :end
            ORDER BY rm.source_weight DESC, rm.published_at DESC
            LIMIT :limit
        """),
        {
            "org_id": org_id,
            "scheme_key": scheme_key,
            "district_key": district_key,
            "start": window_start,
            "end": window_end,
            "limit": limit,
        },
    )
    rows = []
    for row in result.fetchall():
        d = dict(row._mapping)
        if d.get("published_at"):
            d["published_at"] = d["published_at"].isoformat()
        rows.append(d)
    return rows


async def _write_analysis(
    signal_id: str,
    result: SpikeAnalyzerOutput,
    db: AsyncSession,
) -> None:
    await db.execute(
        text("""
            UPDATE sentiment_signals
            SET spike_analysis = CAST(:analysis AS jsonb),
                updated_at = now()
            WHERE id = :id
        """),
        {
            "analysis": json.dumps(result.model_dump()),
            "id": signal_id,
        },
    )
    await db.flush()
