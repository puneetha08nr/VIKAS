"""sentiment.aggregator — Stage 4 daily rollup.

Computes sentiment_signals rows from analyzed_mentions. Pure SQL — no LLM.
Also maintains 7-day rolling scheme_patterns and district_patterns summaries.

Algorithm per (scheme_key, district_key) pair:
  1. Count mentions by polarity for the target date window
  2. Compute plain and source-weight-adjusted polarity averages
  3. Extract dominant themes from analyzed_mentions.themes
  4. Compare current negative rate to 7-day rolling baseline → spike_detected flag
  5. UPSERT sentiment_signals (ON CONFLICT UPDATE)
  6. UPSERT scheme_patterns and district_patterns for 7-day window

spike_detected = True when:
  negative_count / mention_count > 2x (rolling 7-day avg negative rate)
  AND mention_count >= SPIKE_MIN_MENTIONS

Spike analysis (LLM reasoning) is handled by the separate spike_detector agent
(Prompt 8), which reads spike_detected=True rows and writes spike_analysis.

Input params:
  scheme_key    (str, default "") — restrict to one scheme; "" = all active
  district_key  (str, default "") — restrict to one district; "" = all
  signal_date   (str, default "")  — ISO date YYYY-MM-DD; "" = yesterday UTC
  window_hours  (int, default 24)
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register

logger = logging.getLogger(__name__)

_SPIKE_MULTIPLIER = 2.0    # negative rate multiple that triggers spike flag
_SPIKE_MIN_MENTIONS = 5    # minimum total mentions before spike check fires
_ROLLING_DAYS = 7          # days of history for baseline


@register
class SentimentAggregatorAgent(BaseAgent):
    name = "sentiment_aggregator"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        district_key: str = ctx.params.get("district_key", "")
        signal_date_str: str = ctx.params.get("signal_date", "")
        window_hours: int = int(ctx.params.get("window_hours", 24))

        signal_date = _resolve_date(signal_date_str)
        window_start = datetime(
            signal_date.year, signal_date.month, signal_date.day, tzinfo=UTC
        )
        window_end = window_start + timedelta(hours=window_hours)

        pairs = await _fetch_active_pairs(
            scheme_key=scheme_key,
            district_key=district_key,
            window_start=window_start,
            window_end=window_end,
            org_id=ctx.org_id,
            db=ctx.db,
        )

        if not pairs:
            logger.info(
                "aggregator: no analyzed mentions in window %s for org %s",
                signal_date, ctx.org_id,
            )
            return AgentResult(
                status="success",
                data={"signal_date": str(signal_date), "pairs_aggregated": 0},
            )

        signals_written = 0
        spikes_flagged = 0

        for scheme, district in pairs:
            try:
                rows = await _fetch_analyzed(
                    scheme_key=scheme,
                    district_key=district,
                    window_start=window_start,
                    window_end=window_end,
                    org_id=ctx.org_id,
                    db=ctx.db,
                )
                if not rows:
                    continue

                agg = _compute_aggregates(rows)

                # Spike detection — compare to 7-day rolling baseline
                baseline_neg_rate = await _rolling_neg_rate(
                    scheme_key=scheme,
                    district_key=district,
                    before_date=signal_date,
                    days=_ROLLING_DAYS,
                    org_id=ctx.org_id,
                    db=ctx.db,
                )
                current_neg_rate = (
                    agg["negative_count"] / agg["mention_count"]
                    if agg["mention_count"] > 0 else 0.0
                )
                spike = (
                    agg["mention_count"] >= _SPIKE_MIN_MENTIONS
                    and baseline_neg_rate is not None
                    and current_neg_rate > baseline_neg_rate * _SPIKE_MULTIPLIER
                )

                await _upsert_signal(
                    scheme_key=scheme,
                    district_key=district,
                    signal_date=signal_date,
                    window_hours=window_hours,
                    agg=agg,
                    spike_detected=spike,
                    org_id=ctx.org_id,
                    db=ctx.db,
                )
                signals_written += 1
                if spike:
                    spikes_flagged += 1
            except Exception as exc:
                logger.warning(
                    "aggregator: failed pair (%s, %s) — %s", scheme, district, exc
                )

        # Update rolling pattern summaries
        try:
            await _update_scheme_patterns(
                scheme_key=scheme_key,
                signal_date=signal_date,
                org_id=ctx.org_id,
                db=ctx.db,
            )
            await _update_district_patterns(
                district_key=district_key,
                signal_date=signal_date,
                org_id=ctx.org_id,
                db=ctx.db,
            )
        except Exception as exc:
            logger.warning("aggregator: pattern update failed — %s", exc)

        logger.info(
            "aggregator: date=%s signals=%d spikes=%d scheme=%s",
            signal_date, signals_written, spikes_flagged, scheme_key or "(all)",
        )
        return AgentResult(
            status="success",
            data={
                "signal_date": str(signal_date),
                "pairs_aggregated": signals_written,
                "spikes_flagged": spikes_flagged,
                "scheme_key": scheme_key,
                "district_key": district_key,
            },
        )


# ── Aggregation math ──────────────────────────────────────────────────────────

def _compute_aggregates(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    polarity_sum = 0.0
    weighted_sum = 0.0
    weight_total = 0.0
    all_themes: list[str] = []

    for r in rows:
        polarity = str(r.get("polarity") or "neutral")
        counts[polarity] += 1
        score = float(r.get("polarity_score") or 0.0)
        weight = float(r.get("source_weight") or 1.0)
        polarity_sum += score
        weighted_sum += score * weight
        weight_total += weight
        themes = r.get("themes") or []
        if isinstance(themes, list):
            all_themes.extend(str(t) for t in themes)

    n = len(rows)
    dominant = counts.most_common(1)[0][0] if counts else "neutral"

    theme_counts: Counter[str] = Counter(all_themes)
    dominant_themes = [t for t, _ in theme_counts.most_common(5)]

    return {
        "mention_count": n,
        "positive_count": counts.get("positive", 0),
        "negative_count": counts.get("negative", 0),
        "neutral_count": counts.get("neutral", 0),
        "mixed_count": counts.get("mixed", 0),
        "avg_polarity_score": round(polarity_sum / n, 4) if n else None,
        "weighted_avg_polarity_score": (
            round(weighted_sum / weight_total, 4) if weight_total > 0 else None
        ),
        "dominant_polarity": dominant,
        "dominant_themes": dominant_themes,
    }


def _resolve_date(date_str: str) -> date:
    if date_str:
        try:
            return date.fromisoformat(date_str)
        except ValueError:
            pass
    return (datetime.now(UTC) - timedelta(days=1)).date()


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_active_pairs(
    scheme_key: str,
    district_key: str,
    window_start: datetime,
    window_end: datetime,
    org_id: str,
    db: AsyncSession,
) -> list[tuple[str, str]]:
    result = await db.execute(
        text("""
            SELECT DISTINCT am.matched_scheme, am.matched_district
            FROM analyzed_mentions am
            JOIN relevant_mentions rm ON rm.id = am.relevant_mention_id
            WHERE am.org_id = :org_id
              AND rm.status = 'analyzed'
              AND rm.created_at >= :start
              AND rm.created_at < :end
              AND (:scheme_key = '' OR am.matched_scheme = :scheme_key)
              AND (:district_key = '' OR am.matched_district = :district_key)
        """),
        {
            "org_id": org_id,
            "start": window_start,
            "end": window_end,
            "scheme_key": scheme_key,
            "district_key": district_key,
        },
    )
    return [(row[0], row[1]) for row in result.fetchall()]


async def _fetch_analyzed(
    scheme_key: str,
    district_key: str,
    window_start: datetime,
    window_end: datetime,
    org_id: str,
    db: AsyncSession,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT am.polarity, am.polarity_score, am.themes,
                   rm.source_weight
            FROM analyzed_mentions am
            JOIN relevant_mentions rm ON rm.id = am.relevant_mention_id
            WHERE am.org_id = :org_id
              AND am.matched_scheme = :scheme_key
              AND am.matched_district = :district_key
              AND rm.status = 'analyzed'
              AND rm.created_at >= :start
              AND rm.created_at < :end
        """),
        {
            "org_id": org_id,
            "scheme_key": scheme_key,
            "district_key": district_key,
            "start": window_start,
            "end": window_end,
        },
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def _rolling_neg_rate(
    scheme_key: str,
    district_key: str,
    before_date: date,
    days: int,
    org_id: str,
    db: AsyncSession,
) -> float | None:
    """Mean daily negative rate over the last `days` completed days."""
    result = await db.execute(
        text("""
            SELECT AVG(
                CASE WHEN mention_count > 0
                     THEN negative_count::float / mention_count
                     ELSE 0.0 END
            )
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
    if row and row[0] is not None:
        return float(row[0])
    return None


async def _upsert_signal(
    scheme_key: str,
    district_key: str,
    signal_date: date,
    window_hours: int,
    agg: dict[str, Any],
    spike_detected: bool,
    org_id: str,
    db: AsyncSession,
) -> None:
    await db.execute(
        text("""
            INSERT INTO sentiment_signals (
                id, org_id, scheme_key, district_key,
                signal_date, window_hours,
                mention_count, weighted_mention_count,
                positive_count, negative_count, neutral_count, mixed_count,
                avg_polarity_score, weighted_avg_polarity_score,
                dominant_polarity, dominant_themes,
                spike_detected, spike_analysis,
                computed_at, created_at, updated_at
            ) VALUES (
                gen_random_uuid(), :org_id, :scheme_key, :district_key,
                :signal_date, :window_hours,
                :mention_count, :mention_count,
                :positive_count, :negative_count, :neutral_count, :mixed_count,
                :avg_polarity_score, :weighted_avg_polarity_score,
                :dominant_polarity, CAST(:dominant_themes AS jsonb),
                :spike_detected, '{}'::jsonb,
                now(), now(), now()
            )
            ON CONFLICT (org_id, scheme_key, district_key, signal_date, window_hours)
            DO UPDATE SET
                mention_count              = EXCLUDED.mention_count,
                weighted_mention_count     = EXCLUDED.weighted_mention_count,
                positive_count             = EXCLUDED.positive_count,
                negative_count             = EXCLUDED.negative_count,
                neutral_count              = EXCLUDED.neutral_count,
                mixed_count                = EXCLUDED.mixed_count,
                avg_polarity_score         = EXCLUDED.avg_polarity_score,
                weighted_avg_polarity_score = EXCLUDED.weighted_avg_polarity_score,
                dominant_polarity          = EXCLUDED.dominant_polarity,
                dominant_themes            = EXCLUDED.dominant_themes,
                spike_detected             = EXCLUDED.spike_detected,
                computed_at                = now(),
                updated_at                 = now()
        """),
        {
            "org_id": org_id,
            "scheme_key": scheme_key,
            "district_key": district_key,
            "signal_date": signal_date,
            "window_hours": window_hours,
            "mention_count": agg["mention_count"],
            "positive_count": agg["positive_count"],
            "negative_count": agg["negative_count"],
            "neutral_count": agg["neutral_count"],
            "mixed_count": agg["mixed_count"],
            "avg_polarity_score": agg["avg_polarity_score"],
            "weighted_avg_polarity_score": agg["weighted_avg_polarity_score"],
            "dominant_polarity": agg["dominant_polarity"],
            "dominant_themes": json.dumps(agg["dominant_themes"]),
            "spike_detected": spike_detected,
        },
    )
    await db.flush()


async def _update_scheme_patterns(
    scheme_key: str,
    signal_date: date,
    org_id: str,
    db: AsyncSession,
) -> None:
    period_end = signal_date
    period_start = period_end - timedelta(days=_ROLLING_DAYS - 1)

    result = await db.execute(
        text("""
            SELECT scheme_key,
                   SUM(mention_count) AS total,
                   AVG(weighted_avg_polarity_score) AS net_polarity
            FROM sentiment_signals
            WHERE org_id = :org_id
              AND signal_date BETWEEN :start AND :end
              AND (:scheme_key = '' OR scheme_key = :scheme_key)
              AND window_hours = 24
            GROUP BY scheme_key
        """),
        {
            "org_id": org_id,
            "start": period_start,
            "end": period_end,
            "scheme_key": scheme_key,
        },
    )
    for row in result.fetchall():
        sk = str(row[0])
        total = int(row[1] or 0)
        net = float(row[2] or 0.0)
        await db.execute(
            text("""
                INSERT INTO scheme_patterns (
                    id, org_id, scheme_key, period_start, period_end,
                    total_mentions, net_polarity, dominant_themes, top_districts,
                    velocity, trend_direction, created_at, updated_at
                ) VALUES (
                    gen_random_uuid(), :org_id, :scheme_key, :period_start, :period_end,
                    :total, :net, '[]'::jsonb, '[]'::jsonb,
                    0.0, 'stable', now(), now()
                )
                ON CONFLICT DO NOTHING
            """),
            {
                "org_id": org_id,
                "scheme_key": sk,
                "period_start": period_start,
                "period_end": period_end,
                "total": total,
                "net": round(net, 4),
            },
        )
    await db.flush()


async def _update_district_patterns(
    district_key: str,
    signal_date: date,
    org_id: str,
    db: AsyncSession,
) -> None:
    period_end = signal_date
    period_start = period_end - timedelta(days=_ROLLING_DAYS - 1)

    result = await db.execute(
        text("""
            SELECT district_key,
                   SUM(mention_count) AS total,
                   AVG(weighted_avg_polarity_score) AS net_polarity
            FROM sentiment_signals
            WHERE org_id = :org_id
              AND signal_date BETWEEN :start AND :end
              AND (:district_key = '' OR district_key = :district_key)
              AND window_hours = 24
            GROUP BY district_key
        """),
        {
            "org_id": org_id,
            "start": period_start,
            "end": period_end,
            "district_key": district_key,
        },
    )
    for row in result.fetchall():
        dk = str(row[0])
        total = int(row[1] or 0)
        net = float(row[2] or 0.0)
        await db.execute(
            text("""
                INSERT INTO district_patterns (
                    id, org_id, district_key, period_start, period_end,
                    total_mentions, net_polarity, top_schemes, top_themes,
                    velocity, trend_direction, created_at, updated_at
                ) VALUES (
                    gen_random_uuid(), :org_id, :district_key, :period_start, :period_end,
                    :total, :net, '[]'::jsonb, '[]'::jsonb,
                    0.0, 'stable', now(), now()
                )
                ON CONFLICT DO NOTHING
            """),
            {
                "org_id": org_id,
                "district_key": dk,
                "period_start": period_start,
                "period_end": period_end,
                "total": total,
                "net": round(net, 4),
            },
        )
    await db.flush()
