"""
reddit_trends — Tier 3 trend signal source.

Uses Reddit's public JSON search API (no auth required) to gauge keyword
momentum by comparing recent weekly post activity against the monthly baseline.
Handles 429 and network failures silently — returns None to trigger Tier 4.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.reddit.com/search.json"
_TIMEOUT = 10.0
_HEADERS = {"User-Agent": "Vikas-AI-Platform/1.0 (marketing-ai-agent)"}


class RedditTrends:
    """Reddit public search client — Tier 3 trend source."""

    async def get_momentum(self, keyword: str) -> dict[str, Any] | None:
        """Return {"momentum": float, "source": "reddit"} or None on failure."""
        try:
            week_count = await self._post_count(keyword, timeframe="week")
            month_count = await self._post_count(keyword, timeframe="month")
            if week_count is None or month_count is None:
                return None
            momentum = _compute_momentum(week_count, month_count)
            return {"momentum": momentum, "source": "reddit"}
        except Exception as exc:
            logger.debug("reddit_trends: %r failed — %s", keyword, exc)
            return None

    async def _post_count(self, keyword: str, timeframe: str) -> int | None:
        """Count posts matching keyword in the given Reddit timeframe."""
        params = {
            "q": keyword,
            "sort": "new",
            "limit": "100",
            "t": timeframe,
            "type": "link",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            resp = await client.get(_SEARCH_URL, params=params)
            if resp.status_code == 429:
                logger.debug("reddit_trends: rate-limited for %r", keyword)
                return None
            if resp.status_code == 403:
                return None
            resp.raise_for_status()
            children = resp.json().get("data", {}).get("children", [])
            return len(children)


def _compute_momentum(week_count: int, month_count: int) -> float:
    """Compute 0-10 momentum from weekly vs monthly Reddit post ratio.

    week / (month / 4) is the weekly ratio. 1.0 = flat → 5.0 score.
    If month is 0 and week > 0: emerging topic, score 7.5.
    """
    if month_count == 0:
        return 7.5 if week_count > 0 else 5.0
    monthly_weekly_avg = month_count / 4.0
    if monthly_weekly_avg < 1.0:
        return 5.0
    ratio = week_count / monthly_weekly_avg
    return round(min(10.0, max(0.0, ratio * 5.0)), 3)
