"""ContentFetch integration — fetches and extracts text content from web pages.

Subclasses BaseIntegration so all HTTP calls benefit from circuit-breaker and
rate-limiter. fetch_page() never raises — it returns status "failed" or
"skipped" on all error paths so the agent loop never aborts mid-batch.
"""
from __future__ import annotations

import logging
import time
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

_TIMEOUT = 20.0
_RETRIES = 2
_BACKOFF = 1.0
_RETRY_STATUS_CODES = {429, 500, 502, 503}
_MAX_BODY_CHARS = 50_000
_HTML_CONTENT_TYPES = {"text/html", "application/xhtml+xml"}


class ContentFetchIntegration(BaseIntegration):
    name = "content_fetch"
    base_url = ""  # each page has its own URL
    max_requests_per_minute = 30

    async def health_check(self) -> bool:
        return True

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict[str, Any]:
        return {}

    async def fetch_page(self, url: str) -> dict[str, Any]:
        """Fetch url and extract title, body text, word_count.

        Returns dict with keys: title, body, word_count, status.
        status is "ok" | "failed" | "skipped" — never raises.
        """
        if not url.startswith(("http://", "https://")):
            return _empty("skipped")

        try:
            html = await self._get_html(url)
        except Exception as exc:
            logger.warning("content_fetch: failed to fetch %s: %s", url, exc)
            return _empty("failed")

        if html is None:
            return _empty("skipped")

        try:
            extracted = _extract(html)
        except Exception as exc:
            logger.warning("content_fetch: extraction error for %s: %s", url, exc)
            return _empty("failed")

        status = "ok" if extracted["word_count"] > 0 else "skipped"
        return {**extracted, "status": status}

    async def _get_html(self, url: str) -> str | None:
        """GET url with circuit-breaker and rate-limit protection.

        Returns HTML text if content-type is HTML, None for non-HTML responses.
        Raises IntegrationError on network failure after retries.
        """
        if self._circuit.is_open():
            raise CircuitOpenError(self.name, self._circuit.retry_after())

        if not self._bucket.consume():
            raise RateLimitError(self.name, self._bucket.seconds_until_token)

        last_error: Exception | None = None

        for attempt in range(_RETRIES):
            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(
                    timeout=_TIMEOUT,
                    follow_redirects=True,
                    headers={"User-Agent": "vikas-bot/1.0 (competitor research)"},
                ) as client:
                    response = await client.get(url)

                response_ms = int((time.monotonic() - t0) * 1000)
                logger.info(
                    "content_fetch_request",
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

                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                if content_type not in _HTML_CONTENT_TYPES:
                    return None

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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _empty(status: str) -> dict[str, Any]:
    return {"title": "", "body": "", "word_count": 0, "status": status}


def _extract(html: str) -> dict[str, Any]:
    """Parse HTML with BeautifulSoup and return title, body text, word_count."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()[:500]

    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript"]):
        tag.decompose()

    main = soup.find("main") or soup.find("article") or soup.find("body")
    raw_text = main.get_text(separator=" ", strip=True) if main else ""
    body = " ".join(raw_text.split())[:_MAX_BODY_CHARS]
    word_count = len(body.split()) if body else 0

    return {"title": title, "body": body, "word_count": word_count}
