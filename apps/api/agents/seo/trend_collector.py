import asyncio
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import TrendSignalOutput

logger = logging.getLogger(__name__)

_BATCH_SIZE = 5  # pytrends accepts at most 5 keywords per payload


@register
class TrendCollectorAgent(BaseAgent):
    name = "trend_collector"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        keywords: list[str] = ctx.params.get("keywords", [])
        timeframe: str = ctx.params.get("timeframe", "today 3-m")
        geo: str = ctx.params.get("geo", "")

        if not keywords:
            keywords = await _fetch_validated_keywords(ctx.db)

        if not keywords:
            return AgentResult(
                status="success",
                data={"signals_written": 0, "keywords_checked": 0, "message": "No keywords to check"},
            )

        loop = asyncio.get_running_loop()
        signals: list[dict[str, Any]] = []

        for batch in _batches(keywords, _BATCH_SIZE):
            try:
                batch_signals = await loop.run_in_executor(
                    None, _fetch_trends_sync, batch, timeframe, geo
                )
                signals.extend(batch_signals)
            except Exception as exc:
                logger.warning(
                    "trend_collector: pytrends failed for batch %s — using neutral momentum: %s",
                    batch, exc,
                )
                for kw in batch:
                    signals.append({"query": kw, "momentum": 5.0})

        written = await _save_signals(signals, ctx.org_id, ctx.db)

        return AgentResult(
            status="success",
            data={"signals_written": written, "keywords_checked": len(keywords)},
        )


# ── pytrends (sync, runs in thread executor) ──────────────────────────────────

def _fetch_trends_sync(
    keywords: list[str], timeframe: str, geo: str
) -> list[dict[str, Any]]:
    from pytrends.request import TrendReq

    pt = TrendReq(hl="en-US", tz=0)
    pt.build_payload(keywords, timeframe=timeframe, geo=geo)
    df = pt.interest_over_time()

    signals: list[dict[str, Any]] = []

    if df is None or df.empty:
        for kw in keywords:
            signals.append({"query": kw, "momentum": 5.0})
        return signals

    for kw in keywords:
        if kw not in df.columns:
            signals.append({"query": kw, "momentum": 5.0})
            continue

        values = [float(v) for v in df[kw].dropna().tolist() if v is not None]
        signals.append({"query": kw, "momentum": _compute_momentum(values)})

    return signals


def _compute_momentum(values: list[float]) -> float:
    """Convert a 0-100 Google Trends interest series to a 0-10 momentum score.

    Ratio of recent (last 25%) vs baseline (first 75%) interest, scaled so
    1.0 (flat trend) == 5.0, matching the opportunity_scorer fallback.
    """
    n = len(values)
    if n == 0:
        return 5.0

    split = max(1, n * 3 // 4)
    baseline = values[:split]
    recent = values[split:] or values  # guard against edge case n==1

    baseline_avg = sum(baseline) / len(baseline)
    recent_avg = sum(recent) / len(recent)

    if baseline_avg < 1.0:
        # Keyword was dormant; any interest is a strong signal
        return round(min(10.0, recent_avg / 10.0), 3)

    ratio = recent_avg / baseline_avg  # 1.0 = flat, 2.0 = doubled
    return round(min(10.0, max(0.0, ratio * 5.0)), 3)


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_validated_keywords(db: AsyncSession) -> list[str]:
    result = await db.execute(
        text(
            "SELECT keyword FROM keywords WHERE status = 'validated' ORDER BY volume DESC LIMIT 100"
        )
    )
    return [row[0] for row in result.fetchall()]


async def _save_signals(
    signals: list[dict[str, Any]], org_id: str, db: AsyncSession
) -> int:
    written = 0
    for raw in signals:
        try:
            output = TrendSignalOutput(**raw)
        except Exception as exc:
            logger.warning("trend_collector: invalid signal skipped: %s | raw=%s", exc, raw)
            continue

        await db.execute(
            text(
                "INSERT INTO trend_signals (id, org_id, source, query, momentum, detected_at) "
                "VALUES (gen_random_uuid(), :org_id, :source, :query, :momentum, now())"
            ),
            {
                "org_id": org_id,
                "source": output.source,
                "query": output.query,
                "momentum": output.momentum,
            },
        )
        written += 1

    await db.flush()
    return written


# ── Utilities ─────────────────────────────────────────────────────────────────

def _batches(items: list[Any], n: int):
    for i in range(0, len(items), n):
        yield items[i : i + n]
