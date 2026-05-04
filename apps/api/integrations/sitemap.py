"""Sitemap integration — fetches and parses XML sitemaps for competitor monitoring.

Subclasses BaseIntegration so all requests benefit from the circuit-breaker
and token-bucket rate limiter. No auth required (public sitemaps).
"""
from __future__ import annotations

import logging
import time
import xml.etree.ElementTree as ET
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.base import (
    BaseIntegration,
    CircuitOpenError,
    IntegrationError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

_SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
_MAX_URLS = 500
_TIMEOUT = 30.0
_RETRIES = 3
_BACKOFF = 1.0
_RETRY_STATUS_CODES = {429, 500, 502, 503}


class SitemapIntegration(BaseIntegration):
    """Fetches and parses public XML sitemaps via httpx with circuit-breaker protection."""

    name = "sitemap"
    base_url = ""  # not used; each domain has its own URL
    max_requests_per_minute = 10  # polite rate for crawling external sites

    async def health_check(self) -> bool:
        return True

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict[str, Any]:
        return {}

    async def fetch_sitemap(self, domain: str) -> list[str]:
        """Fetch sitemap.xml for domain. Returns discovered page URLs (capped at _MAX_URLS).

        Handles both urlset and sitemapindex formats.
        Raises IntegrationError on network failure or HTTP error.
        """
        domain_clean = domain.replace("https://", "").replace("http://", "").rstrip("/")
        sitemap_url = f"https://{domain_clean}/sitemap.xml"

        xml_text = await self._get_text(sitemap_url)
        urls = _parse_sitemap_xml(xml_text)

        return urls[:_MAX_URLS]

    async def _get_text(self, url: str) -> str:
        """GET a URL with circuit-breaker and rate-limit protection. Returns response text."""
        if self._circuit.is_open():
            raise CircuitOpenError(self.name, self._circuit.retry_after())

        if not self._bucket.consume():
            raise RateLimitError(self.name, self._bucket.seconds_until_token)

        last_error: Exception | None = None

        for attempt in range(_RETRIES):
            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                    response = await client.get(url)
                response_ms = int((time.monotonic() - t0) * 1000)

                logger.info(
                    "sitemap_request",
                    extra={
                        "integration": self.name,
                        "url": url,
                        "status_code": response.status_code,
                        "response_time_ms": response_ms,
                        "attempt": attempt + 1,
                    },
                )

                if response.status_code in _RETRY_STATUS_CODES:
                    last_error = IntegrationError(
                        f"HTTP {response.status_code}", response.status_code, self.name
                    )
                    if attempt < _RETRIES - 1:
                        import asyncio
                        await asyncio.sleep(_BACKOFF * (2 ** attempt))
                    continue

                response.raise_for_status()
                self._circuit.record_success()
                return response.text

            except (CircuitOpenError, RateLimitError, IntegrationError):
                raise
            except httpx.HTTPStatusError as exc:
                self._circuit.record_failure()
                raise IntegrationError(
                    f"HTTP {exc.response.status_code}: {exc}",
                    status_code=exc.response.status_code,
                    integration_name=self.name,
                ) from exc
            except Exception as exc:
                last_error = exc
                if attempt < _RETRIES - 1:
                    import asyncio
                    await asyncio.sleep(_BACKOFF * (2 ** attempt))

        self._circuit.record_failure()
        raise IntegrationError(
            f"All {_RETRIES} attempts failed: {last_error}",
            status_code=None,
            integration_name=self.name,
        ) from last_error


def _parse_sitemap_xml(xml_text: str) -> list[str]:
    """Parse sitemap XML. Returns page URLs from urlset, or sub-sitemap URLs from sitemapindex."""
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        return []

    tag_local = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    if tag_local == "sitemapindex":
        child_tag, loc_tag = "sitemap", "loc"
    else:
        child_tag, loc_tag = "url", "loc"

    urls: list[str] = []
    ns = _SITEMAP_NS

    children = root.findall(f"{{{ns}}}{child_tag}")
    if not children:
        children = root.findall(child_tag)

    for child in children:
        loc_el = child.find(f"{{{ns}}}{loc_tag}")
        if loc_el is None:
            loc_el = child.find(loc_tag)
        if loc_el is not None and loc_el.text:
            urls.append(loc_el.text.strip())

    return urls
