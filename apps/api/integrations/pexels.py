"""PexelsIntegration — searches Pexels for stock video clips.

Extends BaseIntegration for circuit-breaker and rate-limiting.
search_videos() NEVER raises — returns [] when API key is unconfigured
or the request fails.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)

_PEXELS_BASE = "https://api.pexels.com"


class PexelsIntegration(BaseIntegration):
    name = "pexels"
    base_url = _PEXELS_BASE
    max_requests_per_minute = 200  # Pexels free tier: 200/hr effectively

    def __init__(self, api_key: str = "") -> None:
        super().__init__()
        self._api_key = api_key

    async def health_check(self) -> bool:
        return bool(self._api_key) and not self._circuit.is_open()

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict[str, Any]:
        return {}

    async def search_videos(self, query: str, per_page: int = 3) -> list[dict[str, Any]]:
        """Search Pexels for videos matching query.

        Returns list of dicts with: pexels_id, video_url, preview_url, width, height.
        Returns [] on any failure (unconfigured, network error, non-2xx). Never raises.
        """
        if not self._api_key:
            logger.warning("pexels: PEXELS_API_KEY not configured — returning empty results")
            return []

        if self._circuit.is_open():
            logger.warning("pexels: circuit open, skipping search")
            return []

        if not self._bucket.consume():
            logger.warning("pexels: rate limit hit, skipping search")
            return []

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{_PEXELS_BASE}/videos/search",
                    params={"query": query, "per_page": per_page},
                    headers={"Authorization": self._api_key},
                )
            if response.status_code != 200:
                logger.warning("pexels: status %d for query %r", response.status_code, query)
                self._circuit.record_failure()
                return []

            self._circuit.record_success()
            data = response.json()
            results = []
            for v in data.get("videos", []):
                files = v.get("video_files", [])
                # Pick the smallest file for preview, largest for full
                files_sorted = sorted(files, key=lambda f: f.get("width", 0))
                preview = files_sorted[0] if files_sorted else {}
                full = files_sorted[-1] if files_sorted else {}
                results.append({
                    "pexels_id": v.get("id"),
                    "video_url": full.get("link", ""),
                    "preview_url": preview.get("link", ""),
                    "width": full.get("width", 0),
                    "height": full.get("height", 0),
                })
            return results

        except Exception as exc:
            logger.warning("pexels: request failed: %s", exc)
            self._circuit.record_failure()
            return []
