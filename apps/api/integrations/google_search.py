"""GoogleSearchIntegration — Google Custom Search JSON API.

Free tier: 100 queries/day (no credit card required).
Keys needed in .env:
  GOOGLE_SEARCH_API_KEY  — from console.cloud.google.com, Custom Search API enabled
  GOOGLE_SEARCH_CX       — from programmablesearchengine.google.com

Endpoint: https://www.googleapis.com/customsearch/v1
If either key is absent, raises IntegrationError so callers can fall back gracefully.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from integrations.base import BaseIntegration, IntegrationError

logger = logging.getLogger(__name__)

_GOOGLE_CSE_BASE = "https://www.googleapis.com/customsearch"
_MAX_RESULTS_PER_REQUEST = 10  # Google CSE hard cap


class GoogleSearchIntegration(BaseIntegration):
    name = "google_search"
    base_url = _GOOGLE_CSE_BASE
    max_requests_per_minute = 10  # free tier: 100/day — be conservative

    async def health_check(self) -> bool:
        return (
            bool(settings.google_search_api_key)
            and bool(settings.google_search_cx)
            and not self._circuit.is_open()
        )

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict[str, Any]:
        return {}

    async def search(self, query: str, count: int = 5) -> list[dict[str, str]]:
        """Search via Google Custom Search API. Returns [{url, title, snippet}, ...].

        Raises IntegrationError if keys are missing or the request fails.
        """
        key = settings.google_search_api_key
        cx = settings.google_search_cx
        if not key or not cx:
            raise IntegrationError(
                "GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_CX are required",
                status_code=None,
                integration_name=self.name,
            )

        num = min(count, _MAX_RESULTS_PER_REQUEST)
        data = await self.request(
            "GET",
            "/v1",
            params={"key": key, "cx": cx, "q": query, "num": num},
        )

        items = data.get("items", [])
        return [
            {
                "url": item.get("link", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in items
        ]
