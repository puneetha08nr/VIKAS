"""Google News RSS — Stage 1 source for news mentions (no API key required).

Endpoint: https://news.google.com/rss/search?q={query}&hl={lang}&gl=IN&ceid=IN:{lang}
Supports English and Tamil queries.

Parses Atom/RSS XML via stdlib xml.etree — no extra deps.
"""
from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://news.google.com/rss/search"
_TIMEOUT = 15.0
_LANG_CONFIG = {
    "en": {"hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
    "ta": {"hl": "ta", "gl": "IN", "ceid": "IN:ta"},
}


class GoogleNewsRssIntegration:
    """Stateless Google News RSS client — no auth, no circuit breaker needed.

    For high-volume use, wrap calls in a retry loop at the caller level.
    """

    async def fetch_articles(
        self,
        query: str,
        language: str = "en",
        max_results: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch recent Google News articles for query.

        Args:
            query: search string, e.g. "Madurai Smart City scheme"
            language: 'en' or 'ta'
            max_results: RSS feeds return up to 100 items; this caps the return

        Returns list of mention dicts for raw_mentions insertion.
        """
        cfg = _LANG_CONFIG.get(language, _LANG_CONFIG["en"])
        params = urlencode({"q": query, **cfg})
        url = f"{_BASE}?{params}"

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("google_news_rss: fetch failed for %r — %s", query, exc)
            return []

        items = _parse_rss(resp.text)
        results = items[:max_results]
        logger.info(
            "google_news_rss_fetch",
            extra={"query": query, "language": language, "items": len(results)},
        )
        return results

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(_BASE, params={"q": "test", "hl": "en-IN"})
                return r.status_code < 500
        except Exception:
            return False


def _parse_rss(xml_text: str) -> list[dict[str, Any]]:
    """Parse RSS/Atom XML and extract mention dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("google_news_rss: XML parse error — %s", exc)
        return []

    channel = root.find("channel")
    if channel is None:
        return []

    items = channel.findall("item")
    results: list[dict[str, Any]] = []
    for item in items:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source_elem = item.find("source")
        source_text = source_elem.text if source_elem is not None else None
        source_name = source_text.strip() if source_text else ""

        if not link:
            continue

        results.append({
            "external_id": hashlib.sha256(link.encode()).hexdigest()[:32],
            "title": title,
            "body": description,
            "author": "",
            "url": link,
            "published_at": _parse_rfc2822(pub_date),
            "source_identifier": f"google_news:{_slug(source_name or link[:40])}",
            "engagement_raw": {},
        })
    return results


def _parse_rfc2822(date_str: str) -> str | None:
    """Parse RFC 2822 date to ISO 8601 string; returns None on failure."""
    if not date_str:
        return None
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str).isoformat()
    except Exception:
        return None


def _slug(s: str) -> str:
    return s.lower().strip().replace(" ", "_")[:60]
