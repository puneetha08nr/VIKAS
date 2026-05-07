"""
trend_collector — 5-tier fallback trend signal agent.

Tier 1: PyTrends (Google Trends)  — single attempt, no retry, batched 5 at a time
Tier 2: Wikipedia Pageview API    — primary workhorse, per-keyword
Tier 3: Reddit public search      — niche catcher, per-keyword
Tier 4: Google Suggest count      — last free signal, per-keyword
Tier 5: Neutral 5.0               — source="neutral_fallback", never fails

Each keyword walks the chain and stops at the first tier that succeeds.
"""
import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import TrendSignalOutput
from integrations.reddit_trends import RedditTrends
from integrations.wikipedia_trends import WikipediaTrends

logger = logging.getLogger(__name__)

_BATCH_SIZE = 5  # pytrends accepts at most 5 keywords per request
_SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
_SUGGEST_TIMEOUT = 8.0


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
                data={
                    "signals_written": 0,
                    "keywords_checked": 0,
                    "message": "No keywords to check",
                },
            )

        signals = await _collect_with_fallback(keywords, timeframe, geo)
        written = await _save_signals(signals, ctx.org_id, ctx.db)

        source_counts: dict[str, int] = {}
        for sig in signals:
            src = sig.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        logger.info(
            "trend_collector: %d/%d written | sources=%s",
            written,
            len(keywords),
            source_counts,
        )

        return AgentResult(
            status="success",
            data={
                "signals_written": written,
                "keywords_checked": len(keywords),
                "sources": source_counts,
            },
        )


# ── 5-tier fallback pipeline ──────────────────────────────────────────────────

async def _collect_with_fallback(
    keywords: list[str], timeframe: str, geo: str
) -> list[dict[str, Any]]:
    """Walk each keyword through the 5-tier chain, stopping at first success."""
    # pending maps keyword → final signal dict (None = not yet scored)
    pending: dict[str, dict[str, Any] | None] = {kw: None for kw in keywords}

    # ── Tier 1: PyTrends (batched, single attempt per batch) ─────────────────
    loop = asyncio.get_running_loop()
    for batch in _batches(list(pending.keys()), _BATCH_SIZE):
        try:
            batch_signals = await loop.run_in_executor(
                None, _fetch_trends_sync, batch, timeframe, geo
            )
            # Only accept keywords that pytrends actually had data for
            for sig in batch_signals:
                kw = sig.get("query", "")
                if kw in pending:
                    pending[kw] = sig
        except Exception as exc:
            logger.info("trend_collector: tier1 pytrends batch %s failed — %s", batch, exc)

    # ── Tiers 2-4: per-keyword async fallback ─────────────────────────────────
    remaining = [kw for kw, sig in pending.items() if sig is None]
    if remaining:
        wikipedia = WikipediaTrends()
        reddit = RedditTrends()
        results = await asyncio.gather(
            *[_score_keyword_tiers234(kw, wikipedia, reddit) for kw in remaining],
            return_exceptions=True,
        )
        for kw, result in zip(remaining, results):
            if isinstance(result, dict):
                pending[kw] = result
            # exceptions leave pending[kw] = None → Tier 5 below

    # ── Tier 5: neutral_fallback — never fails ────────────────────────────────
    for kw in pending:
        if pending[kw] is None:
            pending[kw] = {"query": kw, "momentum": 5.0, "source": "neutral_fallback"}

    return list(pending.values())  # type: ignore[return-value]


async def _score_keyword_tiers234(
    keyword: str,
    wikipedia: WikipediaTrends,
    reddit: RedditTrends,
) -> dict[str, Any]:
    """Try Tiers 2 → 3 → 4 for one keyword. Always returns a complete signal dict."""
    # Tier 2: Wikipedia pageviews
    result = await wikipedia.get_momentum(keyword)
    if result is not None:
        return {"query": keyword, **result}

    # Tier 3: Reddit post activity
    result = await reddit.get_momentum(keyword)
    if result is not None:
        return {"query": keyword, **result}

    # Tier 4: Google Suggest count
    result = await _google_suggest_momentum(keyword)
    if result is not None:
        return {"query": keyword, **result}

    # Tier 5 — caller handles this (neutral_fallback)
    return {"query": keyword, "momentum": 5.0, "source": "neutral_fallback"}


async def _google_suggest_momentum(keyword: str) -> dict[str, Any] | None:
    """Tier 4: map Google autocomplete suggestion count → momentum signal.

    10 suggestions = strong awareness → ~9.0
    5 suggestions  = moderate         → ~5.0
    0 suggestions  = unknown          → 1.0
    """
    try:
        async with httpx.AsyncClient(timeout=_SUGGEST_TIMEOUT) as client:
            resp = await client.get(
                _SUGGEST_URL,
                params={"client": "firefox", "q": keyword, "hl": "en"},
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            data = resp.json()
            suggestions: list[str] = data[1] if len(data) > 1 else []
            # Exclude the exact keyword itself from count
            count = len([s for s in suggestions if s and s.strip().lower() != keyword.lower()])
            momentum = round(min(10.0, max(1.0, 1.0 + count * 0.9)), 3)
            return {"momentum": momentum, "source": "google_suggest"}
    except Exception as exc:
        logger.debug("trend_collector: tier4 google_suggest failed for %r — %s", keyword, exc)
        return None


# ── PyTrends (sync, runs in thread executor) ──────────────────────────────────

def _fetch_trends_sync(
    keywords: list[str], timeframe: str, geo: str
) -> list[dict[str, Any]]:
    """Fetch Google Trends interest for keywords. Returns only keywords with real data.

    Keywords not found in the response are omitted — caller falls them through to Tier 2.
    """
    from pytrends.request import TrendReq

    pt = TrendReq(hl="en-US", tz=0)
    pt.build_payload(keywords, timeframe=timeframe, geo=geo)
    df = pt.interest_over_time()

    if df is None or df.empty:
        return []  # No data for any keyword — all fall through to Tier 2

    signals: list[dict[str, Any]] = []
    for kw in keywords:
        if kw not in df.columns:
            continue  # No column → no data → fall through to Tier 2
        values = [float(v) for v in df[kw].dropna().tolist() if v is not None]  # type: ignore[union-attr]
        if not values or max(values) == 0:
            continue  # All-zero series → treat as no data → fall through
        signals.append({
            "query": kw,
            "momentum": _compute_momentum(values),
            "source": "google_trends",
        })

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
    recent = values[split:] or values

    baseline_avg = sum(baseline) / len(baseline)
    recent_avg = sum(recent) / len(recent)

    if baseline_avg < 1.0:
        return round(min(10.0, recent_avg / 10.0), 3)

    ratio = recent_avg / baseline_avg
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
