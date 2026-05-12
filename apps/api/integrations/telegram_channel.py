"""Telegram public channel scraper — Stage 1 source.

Scrapes the public web preview of Telegram channels at:
  https://t.me/s/{channel_username}

Works for any public channel without auth. For private channels or
high-volume production use, migrate to Telethon (MTProto) — this file
serves as the integration interface; swap the transport in fetch_messages().

No API key required for public channels.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE_URL = "https://t.me/s"
_TIMEOUT = 15.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}
class TelegramChannelIntegration:
    """Public Telegram channel scraper.

    Fetches and parses https://t.me/s/{channel} HTML to extract messages.
    Rate-limit calls at the agent level — Telegram does not publish a quota
    but throttles aggressive scrapers.
    """

    async def fetch_messages(
        self,
        channel: str,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch recent messages from a public Telegram channel.

        Args:
            channel: username without @, e.g. "MaduraiNewsOfficial"
            max_results: max messages to return from the page

        Returns list of mention dicts for raw_mentions insertion.
        """
        url = f"{_BASE_URL}/{channel.lstrip('@')}"
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, headers=_HEADERS) as client:
                resp = await client.get(url)
                if resp.status_code == 404:
                    logger.warning("telegram_channel: channel %r not found", channel)
                    return []
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("telegram_channel: fetch failed for %r — %s", channel, exc)
            return []

        messages = _parse_messages(resp.text, channel)
        results = messages[:max_results]
        logger.info(
            "telegram_fetch",
            extra={"channel": channel, "messages": len(results)},
        )
        return results

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0, headers=_HEADERS) as client:
                r = await client.get(f"{_BASE_URL}/durov")
                return r.status_code == 200
        except Exception:
            return False


def _parse_messages(html: str, channel: str) -> list[dict[str, Any]]:
    """Extract message text, datetime, and views from Telegram preview HTML."""
    soup = BeautifulSoup(html, "lxml")
    message_divs = soup.find_all("div", class_="tgme_widget_message_wrap")

    results: list[dict[str, Any]] = []
    for wrap in message_divs:
        # Text content
        text_div = wrap.find("div", class_="tgme_widget_message_text")
        if not text_div:
            continue
        text = text_div.get_text(separator=" ", strip=True)
        if not text:
            continue

        # Message ID + URL
        msg_link = wrap.find("a", class_="tgme_widget_message_date")
        msg_url = msg_link["href"] if msg_link else ""
        msg_id = _extract_msg_id(str(msg_url))

        # Datetime
        time_elem = wrap.find("time")
        published_at: str | None = None
        if time_elem and time_elem.get("datetime"):
            published_at = time_elem["datetime"]

        # View count
        views_elem = wrap.find("span", class_="tgme_widget_message_views")
        views_raw = views_elem.get_text(strip=True) if views_elem else ""

        results.append({
            "external_id": f"tg:{channel}:{msg_id}" if msg_id else _hash_id(text),
            "title": "",
            "body": text,
            "author": channel,
            "url": str(msg_url) if msg_url else f"https://t.me/{channel}",
            "published_at": published_at,
            "source_identifier": f"telegram_channel:@{channel}",
            "engagement_raw": {"views_raw": views_raw},
        })
    return results


def _extract_msg_id(url: str) -> str:
    match = re.search(r"/(\d+)$", url)
    return match.group(1) if match else ""


def _hash_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]
