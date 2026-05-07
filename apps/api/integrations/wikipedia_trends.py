"""
wikipedia_trends — Tier 2 trend signal source.

Searches Wikipedia for the best-matching article, then fetches monthly
pageview data from the Wikimedia REST API to compute a momentum score.
No API key required. Rate-limit: Wikimedia asks for a User-Agent header.
"""
from __future__ import annotations

import logging
import urllib.parse
from datetime import date, timedelta
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_SEARCH_URL = "https://en.wikipedia.org/w/api.php"
_PAGEVIEW_BASE = "https://wikimedia.org/api/rest_v1"
_TIMEOUT = 10.0
_HEADERS = {"User-Agent": "Vikas-AI-Platform/1.0 (marketing-ai-agent)"}


class WikipediaTrends:
    """Wikimedia Pageview API client — Tier 2 trend source."""

    async def get_momentum(self, keyword: str) -> dict[str, Any] | None:
        """Return {"momentum": float, "source": "wikipedia"} or None on failure."""
        try:
            article = await self._find_article(keyword)
            if not article:
                return None
            pageviews = await self._monthly_pageviews(article, months=4)
            if len(pageviews) < 2:
                return None
            momentum = _compute_momentum(pageviews)
            return {"momentum": momentum, "source": "wikipedia"}
        except Exception as exc:
            logger.debug("wikipedia_trends: %r failed — %s", keyword, exc)
            return None

    async def _find_article(self, keyword: str) -> str | None:
        """Find best-matching Wikipedia article title via opensearch."""
        params = {
            "action": "opensearch",
            "search": keyword,
            "limit": "1",
            "format": "json",
            "redirects": "resolve",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            resp = await client.get(_SEARCH_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            titles: list[str] = data[1] if len(data) > 1 else []
            return titles[0] if titles else None

    async def _monthly_pageviews(self, article: str, months: int = 4) -> list[int]:
        """Fetch monthly pageview counts for an article (most recent N months)."""
        today = date.today()
        # End: first day of current month (last complete month boundary)
        end = date(today.year, today.month, 1) - timedelta(days=1)
        start = (date(end.year, end.month, 1) - timedelta(days=months * 31)).replace(day=1)

        article_encoded = urllib.parse.quote(article.replace(" ", "_"), safe="")
        url = (
            f"{_PAGEVIEW_BASE}/metrics/pageviews/per-article"
            f"/en.wikipedia/all-access/all-agents/{article_encoded}"
            f"/monthly/{start.strftime('%Y%m')}01/{end.strftime('%Y%m')}01"
        )
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 404:
                return []
            resp.raise_for_status()
            items = resp.json().get("items", [])
            return [int(item["views"]) for item in items]


def _compute_momentum(views: list[int]) -> float:
    """Convert monthly pageview series to 0-10 momentum score.

    Same ratio formula as the PyTrends path: recent (last 25%) vs
    baseline (first 75%). Flat trend → 5.0.
    """
    n = len(views)
    if n == 0:
        return 5.0
    split = max(1, n * 3 // 4)
    baseline = views[:split]
    recent = views[split:] or views
    baseline_avg = sum(baseline) / len(baseline)
    recent_avg = sum(recent) / len(recent)
    if baseline_avg < 100:
        # Very low baseline — any growth is meaningful
        return round(min(10.0, 5.0 + recent_avg / 5000.0), 3)
    ratio = recent_avg / baseline_avg
    return round(min(10.0, max(0.0, ratio * 5.0)), 3)
