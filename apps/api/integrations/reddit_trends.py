"""
reddit_trends — Tier 3 trend signal source.

Single API call: fetch the 100 most recent posts matching the exact keyword
phrase, then split by actual created_utc timestamps:

  recent   = posts in the last 30 days
  baseline = posts in the 30–60 day window

ratio = recent / baseline; flat (1.0) → 5.0, rising → >5, falling → <5.

Using created_utc avoids the limit=100 cap bias that makes t=week vs t=month
always return 100/100 for any moderately active keyword.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://www.reddit.com/search.json"
_TIMEOUT = 10.0
_HEADERS = {"User-Agent": "Vikas-AI-Platform/1.0 (marketing-ai-agent)"}
_RECENT_DAYS = 30
_BASELINE_DAYS = 60
_MIN_POSTS = 3  # fewer posts → no reliable signal → fall to Tier 4


class RedditTrends:
    """Reddit public search client — Tier 3 trend source."""

    async def get_momentum(self, keyword: str) -> dict[str, Any] | None:
        """Return {"momentum": float, "source": "reddit"} or None on failure."""
        try:
            posts = await self._fetch_posts(keyword, limit=100)
            if posts is None:
                return None
            recent, baseline = _split_by_window(posts)
            if recent + baseline < _MIN_POSTS:
                logger.debug(
                    "reddit_trends: too few posts for %r (%d total) — falling through",
                    keyword,
                    recent + baseline,
                )
                return None
            momentum = _compute_momentum(recent, baseline)
            return {"momentum": momentum, "source": "reddit"}
        except Exception as exc:
            logger.debug("reddit_trends: %r failed — %s", keyword, exc)
            return None

    async def _fetch_posts(self, keyword: str, limit: int = 100) -> list[dict[str, Any]] | None:
        """Fetch the most recent posts for the exact keyword phrase."""
        params = {
            "q": f'"{keyword}"',
            "sort": "new",
            "limit": str(limit),
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
            return [child["data"] for child in children]


def _split_by_window(posts: list[dict[str, Any]]) -> tuple[int, int]:
    """Split posts into recent (0-30 days) and baseline (30-60 days) counts.

    Uses created_utc (Unix timestamp) from each post's data dict.
    Posts older than 60 days are ignored — they predate the comparison window.
    """
    now = time.time()
    cutoff_recent = now - _RECENT_DAYS * 86400
    cutoff_baseline = now - _BASELINE_DAYS * 86400

    recent = sum(1 for p in posts if p.get("created_utc", 0) >= cutoff_recent)
    baseline = sum(
        1 for p in posts
        if cutoff_baseline <= p.get("created_utc", 0) < cutoff_recent
    )
    return recent, baseline


def _compute_momentum(recent: int, baseline: int) -> float:
    """Compute 0-10 momentum from recent vs baseline post count ratio.

    baseline == 0 and recent > 0: new/emerging topic → 7.5
    ratio = 1.0 (flat)  → 5.0
    ratio = 2.0 (rising) → 10.0
    ratio = 0.5 (falling) → 2.5
    """
    if baseline == 0:
        return 7.5 if recent > 0 else 5.0
    ratio = recent / baseline
    return round(min(10.0, max(0.0, ratio * 5.0)), 3)
