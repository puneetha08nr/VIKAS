"""YouTube Data API v3 — Stage 1 source for video comments and transcripts.

Fetches:
  1. Videos matching a scheme/district query (search endpoint)
  2. Top-level comments on those videos (commentThreads endpoint)

Key: YOUTUBE_API_KEY env var (Google Cloud Console, YouTube Data API v3 enabled).
Quota: 10,000 units/day; search=100 units, commentThreads=1 unit per request.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from integrations.base import BaseIntegration, IntegrationError

logger = logging.getLogger(__name__)

_BASE = "https://www.googleapis.com/youtube"
_SEARCH_PATH = "/v3/search"
_COMMENTS_PATH = "/v3/commentThreads"


class YouTubeDataIntegration(BaseIntegration):
    name = "youtube_data"
    base_url = _BASE
    max_requests_per_minute = 10

    async def health_check(self) -> bool:
        return bool(settings.youtube_api_key) and not self._circuit.is_open()

    async def get_credentials(self, org_id: str, db: AsyncSession) -> dict[str, Any]:
        return {}

    async def search_videos(
        self,
        query: str,
        max_results: int = 10,
        published_after: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search for videos matching query. Returns list of video summary dicts.

        Args:
            query: e.g. "Madurai Smart City scheme"
            max_results: 1–50
            published_after: RFC 3339 datetime, e.g. "2026-05-01T00:00:00Z"

        Returns list of {video_id, title, description, channel_title,
                          published_at, url}.
        """
        key = settings.youtube_api_key
        if not key:
            raise IntegrationError(
                "YOUTUBE_API_KEY is required",
                status_code=None,
                integration_name=self.name,
            )

        params: dict[str, Any] = {
            "key": key,
            "q": query,
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": "date",
            "relevanceLanguage": "ta",
        }
        if published_after:
            params["publishedAfter"] = published_after

        data = await self.request("GET", _SEARCH_PATH, params=params)
        items = data.get("items", [])
        results: list[dict[str, Any]] = []
        for item in items:
            vid_id = (item.get("id") or {}).get("videoId")
            if not vid_id:
                continue
            snippet = item.get("snippet") or {}
            results.append({
                "video_id": vid_id,
                "title": (snippet.get("title") or "").strip(),
                "description": (snippet.get("description") or "").strip(),
                "channel_title": (snippet.get("channelTitle") or "").strip(),
                "channel_id": (snippet.get("channelId") or "").strip(),
                "published_at": snippet.get("publishedAt"),
                "url": f"https://www.youtube.com/watch?v={vid_id}",
            })
        logger.info(
            "youtube_search", extra={"query": query, "videos": len(results)}
        )
        return results

    async def fetch_comments(
        self,
        video_id: str,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch top-level comments for a video.

        Returns list of mention dicts for raw_mentions insertion:
          {external_id, title, body, author, url, published_at,
           source_identifier, engagement_raw}
        """
        key = settings.youtube_api_key
        if not key:
            raise IntegrationError(
                "YOUTUBE_API_KEY is required",
                status_code=None,
                integration_name=self.name,
            )

        params = {
            "key": key,
            "videoId": video_id,
            "maxResults": min(max_results, 100),
            "textFormat": "plainText",
            "order": "relevance",
        }
        data = await self.request("GET", _COMMENTS_PATH, params=params)
        items = data.get("items", [])
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        results: list[dict[str, Any]] = []
        for item in items:
            comment = (
                (item.get("snippet") or {})
                .get("topLevelComment", {})
                .get("snippet", {})
            )
            text = (comment.get("textDisplay") or "").strip()
            comment_id = item.get("id") or hashlib.sha256(text.encode()).hexdigest()[:32]
            author = (comment.get("authorDisplayName") or "").strip()
            like_count = comment.get("likeCount") or 0
            reply_count = (item.get("snippet") or {}).get("totalReplyCount") or 0
            results.append({
                "external_id": f"yt_comment:{comment_id}",
                "title": "",
                "body": text,
                "author": author,
                "url": f"{video_url}&lc={comment_id}",
                "published_at": comment.get("publishedAt"),
                "source_identifier": f"youtube_video:{video_id}",
                "engagement_raw": {
                    "like_count": like_count,
                    "reply_count": reply_count,
                },
            })
        logger.info(
            "youtube_comments",
            extra={"video_id": video_id, "comments": len(results)},
        )
        return results
