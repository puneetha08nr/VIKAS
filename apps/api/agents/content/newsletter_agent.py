"""newsletter_agent — generates an email newsletter from an article.

Standard tier LLM. Writes to newsletters table.

Input params:
  article_id (str, required)
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import NewsletterAgentOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


@register
class NewsletterAgent(BaseAgent):
    name = "newsletter_agent"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        article_id = str(ctx.params.get("article_id", "")).strip()
        if not article_id:
            return AgentResult(status="failed", error="article_id param is required")

        article = await _load_article(article_id, ctx.org_id, ctx.db)
        if not article:
            return AgentResult(status="failed", error=f"Article '{article_id}' not found")

        template = await PromptRegistry().get(self.name, ctx.db)
        prompt = (
            template
            .replace("ARTICLE_TITLE", article.get("title", ""))
            .replace("ARTICLE_BODY", (article.get("body_html", "") or "")[:2000])
            .replace("KEYWORD", article.get("keyword", ""))
        )

        raw = await self.call_llm(ctx, prompt)
        newsletter = _parse_newsletter(raw, article.get("title", ""))

        nl_id = str(uuid.uuid4())
        await ctx.db.execute(
            text(
                "INSERT INTO newsletters "
                "  (id, org_id, article_id, subject, preview_text, body_html, status, created_at) "
                "VALUES "
                "  (CAST(:id AS uuid), :org_id, CAST(:article_id AS uuid), "
                "   :subject, :preview_text, :body_html, 'draft', now())"
            ),
            {
                "id": nl_id,
                "org_id": ctx.org_id,
                "article_id": article_id,
                "subject": newsletter.get("subject", article.get("title", "")),
                "preview_text": newsletter.get("preview_text", ""),
                "body_html": newsletter.get("body_html", raw.strip()),
            },
        )
        await ctx.db.flush()

        output = NewsletterAgentOutput(
            newsletter_id=nl_id,
            article_id=article_id,
            status="draft",
        )
        return AgentResult(status="success", data=output.model_dump())


async def _load_article(article_id: str, org_id: str, db) -> dict | None:
    result = await db.execute(
        text("SELECT id, keyword, title, body_html FROM articles "
             "WHERE id = CAST(:id AS uuid) AND org_id = :org_id"),
        {"id": article_id, "org_id": org_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "keyword": row[1] or "", "title": row[2] or "", "body_html": row[3] or ""}


def _parse_newsletter(raw: str, fallback_title: str) -> dict:
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```")
        return json.loads(clean)
    except Exception:
        return {"subject": fallback_title, "preview_text": "", "body_html": raw.strip()}
