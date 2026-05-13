"""sentiment.telegram_collector — Stage 1 Telegram public channel collection.

Scrapes public Telegram channels for scheme-related mentions.
Channels to monitor are passed as params (configured per org).

No LLM. Requires no API key for public channels.

Input params:
  scheme_key    (str, required)
  district_key  (str, default "")
  channels      (list[str], required) — public channel usernames, e.g. ["MaduraiNews"]
  max_per_channel (int, default 50)
"""
from __future__ import annotations

import logging

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from integrations.telegram_channel import TelegramChannelIntegration

from ._db import save_mentions

logger = logging.getLogger(__name__)


@register
class TelegramCollectorAgent(BaseAgent):
    name = "sentiment_telegram_collector"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        district_key: str = ctx.params.get("district_key", "")
        channels: list[str] = ctx.params.get("channels", [])
        max_per_channel: int = int(ctx.params.get("max_per_channel", 50))

        if not scheme_key:
            return AgentResult(status="failed", error="scheme_key is required")
        if not channels:
            return AgentResult(status="failed", error="channels list is required")

        integration = TelegramChannelIntegration()
        total_inserted = 0
        total_skipped = 0
        channels_scraped = 0

        for channel in channels:
            if not isinstance(channel, str) or not channel.strip():
                continue
            channel = channel.strip()
            try:
                messages = await integration.fetch_messages(
                    channel=channel,
                    max_results=max_per_channel,
                )
            except Exception as exc:
                logger.warning(
                    "telegram_collector: channel %r failed — %s", channel, exc
                )
                continue

            if not messages:
                logger.info("telegram_collector: no messages from channel %r", channel)
                continue

            inserted, skipped = await save_mentions(
                mentions=messages,
                source="telegram",
                scheme_key=scheme_key,
                district_key=district_key,
                org_id=ctx.org_id,
                db=ctx.db,
            )
            total_inserted += inserted
            total_skipped += skipped
            channels_scraped += 1

        logger.info(
            "telegram_collector: channels=%d inserted=%d skipped=%d scheme=%s",
            channels_scraped, total_inserted, total_skipped, scheme_key,
        )
        return AgentResult(
            status="success",
            data={
                "channels_attempted": len(channels),
                "channels_scraped": channels_scraped,
                "inserted": total_inserted,
                "skipped": total_skipped,
                "scheme_key": scheme_key,
                "district_key": district_key,
            },
        )
