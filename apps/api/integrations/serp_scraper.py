"""SerpScraper integration — scrapes Google SERP HTML and detects AEO features.

Extends BaseIntegration so rate-limiting and circuit-breaker are inherited.
scrape_serp() NEVER raises — all error paths return a dict with found=False
so the agent loop never aborts mid-batch.

Rate: 10 req/min — conservative to avoid triggering bot detection.
Block detection: 429 or 403 → circuit breaker fires.
User-agent rotation: 3 realistic desktop UAs cycled per request.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from integrations.base import BaseIntegration, CircuitOpenError

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0
_GOOGLE_SEARCH_URL = "https://www.google.com/search"
_INTER_REQUEST_DELAY = 2.5   # seconds — polite crawl delay

_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.4.1 Safari/605.1.15"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
]

_EMPTY_RESULT: dict[str, Any] = {
    "found": False,
    "blocked": False,
    "ai_overview": False,
    "featured_snippet": False,
    "paa_count": 0,
    "organic_position": None,
}


class SerpScraperIntegration(BaseIntegration):
    name = "serp_scraper"
    base_url = "https://www.google.com"
    max_requests_per_minute = 10

    def __init__(self) -> None:
        super().__init__()
        self._ua_index = 0

    async def health_check(self) -> bool:
        return not self._circuit.is_open()

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict[str, Any]:
        return {}

    async def scrape_serp(self, keyword: str, domain: str | None = None) -> dict[str, Any]:
        """Fetch SERP for keyword and detect AEO features.

        Returns dict with keys:
          found (bool), blocked (bool), ai_overview (bool),
          featured_snippet (bool), paa_count (int),
          organic_position (int | None)

        Never raises.
        """
        if self._circuit.is_open():
            logger.warning("serp_scraper: circuit open, skipping %r", keyword)
            return {**_EMPTY_RESULT, "blocked": True}

        if not self._bucket.consume():
            logger.warning("serp_scraper: rate limit hit for %r", keyword)
            return {**_EMPTY_RESULT}

        ua = _USER_AGENTS[self._ua_index % len(_USER_AGENTS)]
        self._ua_index += 1

        headers = {
            "User-Agent": ua,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        params = {"q": keyword, "hl": "en", "num": 10}

        await asyncio.sleep(_INTER_REQUEST_DELAY)

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=_TIMEOUT,
                follow_redirects=True,
            ) as client:
                response = await client.get(
                    _GOOGLE_SEARCH_URL, params=params, headers=headers
                )

            ms = int((time.monotonic() - t0) * 1000)
            logger.info(
                "serp_scraper_request",
                extra={
                    "keyword": keyword,
                    "status_code": response.status_code,
                    "response_ms": ms,
                },
            )

            if response.status_code in {403, 429}:
                self._circuit.record_failure()
                logger.warning(
                    "serp_scraper: blocked (HTTP %s) for %r — circuit recording failure",
                    response.status_code, keyword,
                )
                return {**_EMPTY_RESULT, "blocked": True}

            response.raise_for_status()
            self._circuit.record_success()

            result = _parse_serp_html(response.text, domain=domain)
            result["found"] = True
            result["blocked"] = False
            return result

        except CircuitOpenError:
            return {**_EMPTY_RESULT, "blocked": True}
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            logger.warning(
                "serp_scraper: error scraping %r after %dms: %s", keyword, elapsed, exc
            )
            self._circuit.record_failure()
            return {**_EMPTY_RESULT}


# ── HTML parsing ──────────────────────────────────────────────────────────────

def _parse_serp_html(html: str, domain: str | None = None) -> dict[str, Any]:
    """Parse Google SERP HTML and return AEO feature flags."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    ai_overview = _detect_ai_overview(soup)
    featured_snippet = _detect_featured_snippet(soup)
    paa_count = _count_paa(soup)
    organic_position = _find_organic_position(soup, domain) if domain else None

    return {
        "ai_overview": ai_overview,
        "featured_snippet": featured_snippet,
        "paa_count": paa_count,
        "organic_position": organic_position,
    }


def _detect_ai_overview(soup: Any) -> bool:
    # AI Overview container: div with id containing "aiob", class "TzHB6b",
    # or newer "AIOverview" / "ai-overview" patterns
    if soup.find(id=lambda i: i and "aiob" in i.lower()):
        return True
    if soup.find(class_="TzHB6b"):
        return True
    if soup.find(attrs={"data-hveid": True, "class": lambda c: c and "ai" in " ".join(c).lower()}):
        return True
    # text-based fallback: "AI Overview" heading present
    for tag in soup.find_all(["h2", "h3", "div"]):
        text = tag.get_text(strip=True)
        if text.lower().startswith("ai overview"):
            return True
    return False


def _detect_featured_snippet(soup: Any) -> bool:
    # Featured snippet: div.V3FYCf (long-standing class), div.xpdopen, or
    # element with data-tts attribute (text-to-speech annotation)
    if soup.find(class_="V3FYCf"):
        return True
    if soup.find(class_="xpdopen"):
        return True
    if soup.find(attrs={"data-tts": True}):
        return True
    # Fallback: div with role="heading" inside a highlighted answer box
    if soup.find("div", attrs={"data-attrid": lambda a: a and "answer" in str(a).lower()}):
        return True
    return False


def _count_paa(soup: Any) -> int:
    # People Also Ask: div.related-question-pair or div[jsname="yEVEwb"]
    count = len(soup.find_all(class_="related-question-pair"))
    if count == 0:
        count = len(soup.find_all(attrs={"jsname": "yEVEwb"}))
    # Fallback: g-accordion-expander (another known PAA wrapper class)
    if count == 0:
        count = len(soup.find_all(class_="g-accordion-expander"))
    return count


def _find_organic_position(soup: Any, domain: str) -> int | None:
    """Return 1-based position of domain in organic results, or None if not found."""
    domain_lower = domain.lower().lstrip("www.").rstrip("/")
    position = 0
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if href.startswith("/url?q=") or href.startswith("http"):
            position += 1
            if domain_lower in href.lower():
                return position
            if position >= 10:
                break
    return None
