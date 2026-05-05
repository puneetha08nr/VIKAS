"""WordPress REST API integration.

Publishes articles to a self-hosted WordPress site using Application Passwords.
"""
from __future__ import annotations

import base64
import logging
from typing import Any

from integrations.base import BaseIntegration

logger = logging.getLogger(__name__)


class WordPressIntegration(BaseIntegration):
    name = "wordpress"
    max_requests_per_minute = 60

    def __init__(self, site_url: str, username: str, app_password: str) -> None:
        super().__init__()
        self.site_url = site_url.rstrip("/")
        credentials = f"{username}:{app_password}"
        self._auth_header = "Basic " + base64.b64encode(credentials.encode()).decode()

    async def health_check(self) -> bool:
        try:
            result = await self.request("GET", f"{self.site_url}/wp-json/wp/v2/posts?per_page=1")
            return isinstance(result, list)
        except Exception:
            return False

    async def create_post(
        self,
        title: str,
        content: str,
        status: str = "draft",
        slug: str = "",
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": title,
            "content": content,
            "status": status,
        }
        if slug:
            payload["slug"] = slug
        if meta:
            payload["meta"] = meta

        return await self.request(
            "POST",
            f"{self.site_url}/wp-json/wp/v2/posts",
            json=payload,
            headers={"Authorization": self._auth_header},
        )

    async def update_post(self, post_id: int, data: dict[str, Any]) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"{self.site_url}/wp-json/wp/v2/posts/{post_id}",
            json=data,
            headers={"Authorization": self._auth_header},
        )
