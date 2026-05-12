"""NewsAPI.org — Stage 1 source for English news mentions.

Free tier: 100 requests/day, developer plan: 250k/month.
Key: NEWSAPI_KEY env var.

Returns mentions shaped for raw_mentions inserts.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from integrations.base import BaseIntegration, IntegrationError

logger = logging.getLogger(__name__)

_BASE = "https://newsapi.org"
_ENDPOINT = "/v2/everything"


class NewsApiIntegration(BaseIntegration):
    name = "newsapi"
    base_url = _BASE
    max_requests_per_minute = 5  # free tier: 100/day → ~4/hr; developer: safe at 5/min

    async def health_check(self) -> bool:
        return bool(settings.newsapi_key) and not self._circuit.is_open()

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict[str, Any]:
        return {}

    async def fetch_articles(
        self,
        query: str,
        from_date: str,
        page_size: int = 20,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Fetch news articles matching query published since from_date.

        Args:
            query: search query — scheme name + district, e.g. "Madurai Smart City"
            from_date: ISO date string, e.g. "2026-05-10"
            page_size: max 100
            language: 'en' for English; NewsAPI doesn't support Tamil

        Returns list of dicts ready for raw_mentions insertion:
          {external_id, title, body, author, url, published_at,
           source_identifier, engagement_raw}
        """
        key = settings.newsapi_key
        if not key:
            raise IntegrationError(
                "NEWSAPI_KEY is required", status_code=None, integration_name=self.name
            )

        data = await self.request(
            "GET",
            _ENDPOINT,
            params={
                "q": query,
                "apiKey": key,
                "from": from_date,
                "pageSize": min(page_size, 100),
                "language": language,
                "sortBy": "publishedAt",
            },
        )

        articles = data.get("articles", [])
        results: list[dict[str, Any]] = []
        for art in articles:
            url = art.get("url") or ""
            if not url:
                continue
            source_name = (art.get("source") or {}).get("name") or ""
            results.append({
                "external_id": _stable_id(url),
                "title": (art.get("title") or "").strip(),
                "body": (art.get("content") or art.get("description") or "").strip(),
                "author": (art.get("author") or "").strip(),
                "url": url,
                "published_at": art.get("publishedAt"),
                "source_identifier": f"newsapi:{_slug(source_name)}",
                "engagement_raw": {},
            })

        logger.info(
            "newsapi_fetch", extra={"query": query, "articles": len(results)}
        )
        return results


def _stable_id(url: str) -> str:
    """Short deterministic ID from URL — avoids storing full URLs as external_id."""
    import hashlib
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def _slug(name: str) -> str:
    return quote_plus(name.lower().strip())[:80]
