"""sentiment.google_news_collector — Stage 1 Google News RSS collection.

Fetches recent news from Google News RSS for a scheme+district query.
Supports English and Tamil queries (controlled by TAMIL_OUTPUT_ENABLED flag).
No API key required. No LLM.

Input params:
  scheme_key     (str, required) — scheme name/key
  district_key   (str, default "") — district filter
  lookback_hours (int, default 24) — not enforced by RSS; included for pipeline parity
  max_results    (int, default 30) — max articles per language
  language       (str, default "en") — "en", "ta", or "both"
"""
from __future__ import annotations

import logging

from config.settings import settings
from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from integrations.google_news_rss import GoogleNewsRssIntegration

from ._db import save_mentions

logger = logging.getLogger(__name__)


@register
class GoogleNewsCollectorAgent(BaseAgent):
    name = "sentiment_google_news_collector"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        district_key: str = ctx.params.get("district_key", "")
        max_results: int = int(ctx.params.get("max_results", 30))
        language: str = ctx.params.get("language", "en")

        if not scheme_key:
            return AgentResult(status="failed", error="scheme_key is required")

        integration = GoogleNewsRssIntegration()

        query = f"{scheme_key} {district_key}".strip()
        languages: list[str] = []

        if language in ("en", "both"):
            languages.append("en")
        if language in ("ta", "both") and settings.tamil_output_enabled:
            languages.append("ta")
        if not languages:
            languages = ["en"]

        total_inserted = 0
        total_skipped = 0
        total_attempted = 0

        for lang in languages:
            articles = await integration.fetch_articles(
                query=query, language=lang, max_results=max_results
            )
            total_attempted += len(articles)
            inserted, skipped = await save_mentions(
                mentions=articles,
                source="google_news_rss",
                scheme_key=scheme_key,
                district_key=district_key,
                org_id=ctx.org_id,
                db=ctx.db,
            )
            total_inserted += inserted
            total_skipped += skipped

        logger.info(
            "google_news_collector: inserted=%d skipped=%d scheme=%s district=%s",
            total_inserted, total_skipped, scheme_key, district_key,
        )
        return AgentResult(
            status="success",
            data={
                "inserted": total_inserted,
                "skipped": total_skipped,
                "attempted": total_attempted,
                "languages": languages,
                "scheme_key": scheme_key,
                "district_key": district_key,
            },
        )
