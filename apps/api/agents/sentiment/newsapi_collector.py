"""sentiment.newsapi_collector — Stage 1 English news collection.

Fetches recent news articles from NewsAPI.org for a scheme+district query
and inserts them into raw_mentions. No LLM — pure data collection.

Input params:
  scheme_key     (str, required) — scheme name/key, e.g. "Madurai Smart City"
  district_key   (str, default "") — district filter, e.g. "Madurai"
  lookback_hours (int, default 24) — collect articles published in this window
  max_results    (int, default 50) — max articles per run
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from integrations.newsapi import NewsApiIntegration

from ._db import save_mentions

logger = logging.getLogger(__name__)


@register
class NewsApiCollectorAgent(BaseAgent):
    name = "sentiment_newsapi_collector"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        district_key: str = ctx.params.get("district_key", "")
        lookback_hours: int = int(ctx.params.get("lookback_hours", 24))
        max_results: int = int(ctx.params.get("max_results", 50))

        if not scheme_key:
            return AgentResult(status="failed", error="scheme_key is required")

        integration = NewsApiIntegration()
        if not await integration.health_check():
            return AgentResult(
                status="failed",
                error="NewsAPI unavailable — NEWSAPI_KEY missing or circuit open",
            )

        query = f"{scheme_key} {district_key} India".strip()
        from_date = (
            datetime.now(UTC) - timedelta(hours=lookback_hours)
        ).strftime("%Y-%m-%dT%H:%M:%S")

        try:
            articles = await integration.fetch_articles(
                query=query,
                from_date=from_date,
                page_size=min(max_results, 100),
            )
        except Exception as exc:
            logger.error("newsapi_collector: fetch failed — %s", exc)
            return AgentResult(status="failed", error=str(exc))

        inserted, skipped = await save_mentions(
            mentions=articles,
            source="newsapi",
            scheme_key=scheme_key,
            district_key=district_key,
            org_id=ctx.org_id,
            db=ctx.db,
        )

        logger.info(
            "newsapi_collector: inserted=%d skipped=%d scheme=%s district=%s",
            inserted, skipped, scheme_key, district_key,
        )
        return AgentResult(
            status="success",
            data={
                "inserted": inserted,
                "skipped": skipped,
                "attempted": len(articles),
                "scheme_key": scheme_key,
                "district_key": district_key,
            },
        )
