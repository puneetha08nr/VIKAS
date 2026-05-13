"""sentiment.youtube_collector — Stage 1 YouTube video comment collection.

For each scheme+district query:
  1. Search for relevant videos (YouTube Data API v3 search)
  2. Fetch top-level comments from each video (commentThreads endpoint)
  3. Insert each comment as a raw_mention

YouTube Data API quota:
  - search: 100 units/call
  - commentThreads: 1 unit/call
  - Free tier: 10,000 units/day

No LLM.

Input params:
  scheme_key     (str, required)
  district_key   (str, default "")
  lookback_hours (int, default 72) — used for publishedAfter filter
  max_videos     (int, default 5) — videos to fetch comments from
  comments_per_video (int, default 50)
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from integrations.youtube_data import YouTubeDataIntegration

from ._db import save_mentions

logger = logging.getLogger(__name__)


@register
class YouTubeCollectorAgent(BaseAgent):
    name = "sentiment_youtube_collector"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        district_key: str = ctx.params.get("district_key", "")
        lookback_hours: int = int(ctx.params.get("lookback_hours", 72))
        max_videos: int = int(ctx.params.get("max_videos", 5))
        comments_per_video: int = int(ctx.params.get("comments_per_video", 50))

        if not scheme_key:
            return AgentResult(status="failed", error="scheme_key is required")

        integration = YouTubeDataIntegration()
        if not await integration.health_check():
            return AgentResult(
                status="failed",
                error="YouTube integration unavailable — YOUTUBE_API_KEY missing?",
            )

        published_after = (
            datetime.now(UTC) - timedelta(hours=lookback_hours)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        query = f"{scheme_key} {district_key}".strip()

        try:
            videos = await integration.search_videos(
                query=query,
                max_results=max_videos,
                published_after=published_after,
            )
        except Exception as exc:
            logger.error("youtube_collector: search failed — %s", exc)
            return AgentResult(status="failed", error=str(exc))

        total_inserted = 0
        total_skipped = 0
        videos_fetched = 0

        for video in videos:
            video_id: str = video.get("video_id", "")
            if not video_id:
                continue
            try:
                comments = await integration.fetch_comments(
                    video_id=video_id,
                    max_results=comments_per_video,
                )
            except Exception as exc:
                logger.warning(
                    "youtube_collector: comments failed for video %s — %s", video_id, exc
                )
                continue

            inserted, skipped = await save_mentions(
                mentions=comments,
                source="youtube",
                scheme_key=scheme_key,
                district_key=district_key,
                org_id=ctx.org_id,
                db=ctx.db,
            )
            total_inserted += inserted
            total_skipped += skipped
            videos_fetched += 1

        logger.info(
            "youtube_collector: videos=%d inserted=%d skipped=%d scheme=%s",
            videos_fetched, total_inserted, total_skipped, scheme_key,
        )
        return AgentResult(
            status="success",
            data={
                "videos_found": len(videos),
                "videos_fetched": videos_fetched,
                "inserted": total_inserted,
                "skipped": total_skipped,
                "scheme_key": scheme_key,
                "district_key": district_key,
            },
        )
