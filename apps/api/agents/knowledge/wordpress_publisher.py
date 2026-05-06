"""wordpress_publisher — publishes an approved article to WordPress.

No LLM call. Reads article from articles table, calls WordPress REST API,
updates articles table with published_url.

Input params:
  article_id (str, required)
  wp_status  (str, optional — publish | draft, default: draft)
"""
from __future__ import annotations

import logging
import os
import re

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import WordPressPublisherOutput
from integrations.wordpress import WordPressIntegration

logger = logging.getLogger(__name__)


@register
class WordPressPublisherAgent(BaseAgent):
    name = "wordpress_publisher"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        article_id = str(ctx.params.get("article_id", "")).strip()
        if not article_id:
            return AgentResult(status="failed", error="article_id param is required")

        wp_status = str(ctx.params.get("wp_status", "draft")).strip()
        if wp_status not in {"publish", "draft"}:
            wp_status = "draft"

        article = await _load_article(article_id, ctx.org_id, ctx.db)
        if not article:
            return AgentResult(status="failed", error=f"Article '{article_id}' not found")

        wp = _build_integration(ctx)
        if wp is None:
            return AgentResult(
                status="failed",
                error=(
                    "WordPress integration not configured — "
                    "set WORDPRESS_URL, WORDPRESS_USERNAME, WORDPRESS_APP_PASSWORD"
                ),
            )

        try:
            post = await wp.create_post(
                title=article["title"],
                content=article["body_html"],
                status=wp_status,
                slug=_slugify(article["title"]),
            )
        except Exception as exc:
            logger.exception("wordpress_publisher: API call failed for article %s", article_id)
            return AgentResult(status="failed", error=f"WordPress API error: {exc}")

        wp_post_id = int(post.get("id", 0))
        published_url = str(post.get("link", ""))

        await ctx.db.execute(
            text(
                "UPDATE articles SET published_url = :url, status = :status "
                "WHERE id = CAST(:id AS uuid) AND org_id = :org_id"
            ),
            {
                "url": published_url,
                "status": "published" if wp_status == "publish" else "draft",
                "id": article_id,
                "org_id": ctx.org_id,
            },
        )
        await ctx.db.flush()

        output = WordPressPublisherOutput(
            article_id=article_id,
            published_url=published_url,
            wp_post_id=wp_post_id,
            status="published" if wp_status == "publish" else "draft",
        )
        return AgentResult(status="success", data=output.model_dump())


def _build_integration(ctx: AgentContext) -> WordPressIntegration | None:
    site_url = os.environ.get("WORDPRESS_URL", "")
    username = os.environ.get("WORDPRESS_USERNAME", "")
    app_password = os.environ.get("WORDPRESS_APP_PASSWORD", "")
    if not all([site_url, username, app_password]):
        return None
    return WordPressIntegration(site_url=site_url, username=username, app_password=app_password)


async def _load_article(article_id: str, org_id: str, db) -> dict | None:
    result = await db.execute(
        text("SELECT id, title, body_html FROM articles "
             "WHERE id = CAST(:id AS uuid) AND org_id = :org_id"),
        {"id": article_id, "org_id": org_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "title": row[1] or "", "body_html": row[2] or ""}


def _slugify(title: str) -> str:
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = slug.strip("-")
    return slug[:100]
