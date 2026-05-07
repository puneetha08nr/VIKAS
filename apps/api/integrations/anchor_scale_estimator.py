"""
anchor_scale_estimator — Tier 3 keyword metric estimator.

Uses same-topic DB anchors + PyTrends ratios + Google Suggest count to
produce rough estimates when Tier 1 (DataForSEO) and Tier 2 (Keywords
Everywhere) are unavailable. Pipeline continuity over accuracy — never
blocks.

data_source for results: 'estimated' (has estimates) or 'pending' (no anchors).
confidence: 'low' always — caller must request true-up when real APIs restore.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

_MIN_VOLUME = 100
_MAX_VOLUME = 500_000
_ANCHOR_LIMIT = 5


class AnchorScaleEstimator(BaseIntegration):
    """Tier 3 estimator — DB anchors + PyTrends + Google Suggest."""

    name = "anchor_scale_estimator"
    base_url = "https://suggestqueries.google.com"
    max_requests_per_minute = 20

    async def health_check(self) -> bool:
        return True

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict:
        return {}

    # ── Public entry point ────────────────────────────────────────────────────

    async def estimate_metrics(
        self,
        keywords: list[str],
        seed_topic: str,
        db: AsyncSession,
    ) -> list[dict[str, Any]]:
        """Estimate volume/KD/CPC for keywords using same-topic DB anchors.

        Returns one dict per keyword. data_source='estimated' when estimates
        were produced, data_source='pending' when no anchors were found.
        """
        if not keywords:
            return []

        # Step 1: Same-topic anchors from DB
        anchors = await _fetch_same_topic_anchors(seed_topic, db)
        if not anchors:
            logger.warning(
                "anchor_scale_estimator: No same-topic anchors found for '%s'"
                " — skipping estimation, saving as pending",
                seed_topic,
            )
            return _all_pending(keywords)

        # Step 2: PyTrends scores for anchors + new keywords
        anchor_texts = [a["keyword"] for a in anchors]
        all_targets = anchor_texts + keywords

        trend_scores: dict[str, float] = {}
        pytrends_ok = False
        try:
            trend_scores = await _get_pytrends_scores(all_targets)
            pytrends_ok = bool(trend_scores)
        except Exception as exc:
            logger.warning(
                "anchor_scale_estimator: PyTrends failed (%s)"
                " — skipping volume estimation, using KD only",
                exc,
            )

        # Steps 3-5: Per-keyword estimation
        anchor_avg_cpc = _anchor_avg_cpc(anchors)
        results: list[dict[str, Any]] = []

        for kw in keywords:
            best_anchor = _closest_anchor(kw, anchors)

            # Step 3: Volume from PyTrends ratio
            estimated_volume: int | None = None
            anchor_kw: str | None = best_anchor["keyword"] if best_anchor else None

            if pytrends_ok and best_anchor:
                new_score = trend_scores.get(kw, 0.0)
                anchor_score = trend_scores.get(best_anchor["keyword"], 0.0)
                if anchor_score > 0 and new_score > 0:
                    raw = (new_score / anchor_score) * best_anchor["volume"] / 100 * 100
                    if _MIN_VOLUME <= raw <= _MAX_VOLUME:
                        estimated_volume = int(round(raw / 100) * 100)
                    else:
                        # Out of caps — fall back to anchor volume
                        estimated_volume = int(best_anchor["volume"])

            # Step 4: KD from Google Suggest count
            kd_estimate = await _kd_from_suggest(kw)

            # Step 5: CPC from anchor average adjusted by KD
            estimated_cpc: float | None = None
            if anchor_avg_cpc is not None and kd_estimate is not None:
                estimated_cpc = round(anchor_avg_cpc * (kd_estimate / 5.0), 2)

            if estimated_volume is None and kd_estimate is None:
                results.append(_pending_row(kw))
            else:
                results.append({
                    "keyword": kw,
                    "volume": estimated_volume,
                    "kd": kd_estimate,
                    "cpc": estimated_cpc,
                    "data_source": "estimated",
                    "confidence": "low",
                    "anchor_keyword": anchor_kw,
                    "true_up_required": True,
                })

        return results


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_same_topic_anchors(
    seed_topic: str, db: AsyncSession
) -> list[dict[str, Any]]:
    """Return up to 5 high-volume anchors whose topic overlaps seed_topic."""
    result = await db.execute(
        text(
            "SELECT keyword, volume, kd, cpc "
            "FROM keywords "
            "WHERE data_source IN ('dataforseo', 'keywords_everywhere') "
            "  AND volume IS NOT NULL "
            "  AND ( "
            "    keyword ILIKE '%' || :seed || '%' "
            "    OR :seed ILIKE '%' || split_part(keyword, ' ', 1) || '%' "
            "  ) "
            "ORDER BY volume DESC "
            "LIMIT :lim"
        ),
        {"seed": seed_topic.lower(), "lim": _ANCHOR_LIMIT},
    )
    return [dict(row) for row in result.mappings().all()]


# ── PyTrends ──────────────────────────────────────────────────────────────────

async def _get_pytrends_scores(keywords: list[str]) -> dict[str, float]:
    """Return {keyword: trend score 0-100}. Runs sync pytrends in thread."""
    return await asyncio.to_thread(_pytrends_sync, list(keywords))


def _pytrends_sync(keywords: list[str]) -> dict[str, float]:
    """Blocking pytrends call — called via asyncio.to_thread only."""
    from pytrends.request import TrendReq  # type: ignore[import-untyped]

    scores: dict[str, float] = {}
    # pytrends max 5 keywords per request; use batches of 4 to leave headroom
    for i in range(0, len(keywords), 4):
        batch = keywords[i : i + 4]
        try:
            pt = TrendReq(hl="en-US", tz=360, timeout=(5, 15), retries=1)
            pt.build_payload(batch, timeframe="today 3-m")
            df = pt.interest_over_time()
            if df is not None and not df.empty:
                for kw in batch:
                    if kw in df.columns:
                        scores[kw] = float(df[kw].mean())
        except Exception as exc:
            logger.warning(
                "anchor_scale_estimator: pytrends batch %d failed: %s", i // 4, exc
            )
    return scores


# ── KD from Google Suggest count ──────────────────────────────────────────────

async def _kd_from_suggest(keyword: str) -> float | None:
    """Map Google Suggest count → KD proxy. Returns None on network error."""
    try:
        count = await _fetch_suggest_count(keyword)
        if count >= 10:
            return 7.0
        if count >= 5:
            return 5.0
        if count >= 3:
            return 4.0
        return 2.0
    except Exception as exc:
        logger.warning(
            "anchor_scale_estimator: suggest count failed for '%s': %s", keyword, exc
        )
        return None


async def _fetch_suggest_count(keyword: str) -> int:
    url = "https://suggestqueries.google.com/complete/search"
    async with httpx.AsyncClient(timeout=8) as client:
        r = await client.get(
            url, params={"q": keyword, "client": "firefox", "hl": "en"}
        )
        r.raise_for_status()
        data = r.json()
        suggestions = data[1] if len(data) > 1 else []
        return len([s for s in suggestions if s and s.strip() != keyword])


# ── Similarity + ranking helpers ──────────────────────────────────────────────

def _closest_anchor(
    keyword: str, anchors: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return the anchor most topically similar to keyword."""
    if not anchors:
        return None
    scored = [(a, _topic_similarity(keyword, a["keyword"])) for a in anchors]
    scored.sort(key=lambda x: (x[1], x[0].get("volume") or 0), reverse=True)
    best_anchor, best_sim = scored[0]
    return best_anchor if best_sim > 0 else anchors[0]


def _topic_similarity(kw1: str, kw2: str) -> float:
    w1 = set(kw1.lower().split())
    w2 = set(kw2.lower().split())
    if not w1 or not w2:
        return 0.0
    return len(w1 & w2) / max(len(w1), len(w2))


def _anchor_avg_cpc(anchors: list[dict[str, Any]]) -> float | None:
    cpcs = [float(a["cpc"]) for a in anchors if a.get("cpc") is not None]
    return round(sum(cpcs) / len(cpcs), 2) if cpcs else None


def _all_pending(keywords: list[str]) -> list[dict[str, Any]]:
    return [_pending_row(kw) for kw in keywords]


def _pending_row(keyword: str) -> dict[str, Any]:
    return {
        "keyword": keyword,
        "volume": None,
        "kd": None,
        "cpc": None,
        "data_source": "pending",
        "confidence": None,
        "anchor_keyword": None,
        "true_up_required": True,
    }
