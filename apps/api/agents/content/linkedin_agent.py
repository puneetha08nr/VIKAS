"""linkedin_agent — generates a LinkedIn post from an article.

Standard tier LLM. Writes to linkedin_posts table.

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
from core.contracts import LinkedInAgentOutput
from core.preference_loader import load_preferences
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


@register
class LinkedInAgent(BaseAgent):
    name = "linkedin_agent"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        article_id = str(ctx.params.get("article_id", "")).strip()
        article_plan_id = str(ctx.params.get("article_plan_id", "")).strip()

        if not article_id and not article_plan_id:
            return AgentResult(status="failed", error="article_id or article_plan_id param is required")

        # Prefer plan (cheaper — outline only) over full article
        if article_plan_id:
            source = await _load_plan(article_plan_id, ctx.org_id, ctx.db)
            if not source:
                return AgentResult(status="failed", error=f"Article plan '{article_plan_id}' not found")
            article_id = article_plan_id  # use plan_id as reference
        else:
            source = await _load_article(article_id, ctx.org_id, ctx.db)
            if not source:
                return AgentResult(status="failed", error=f"Article '{article_id}' not found")

        learned_preferences = await load_preferences(ctx.org_id, "linkedin", ctx.db)
        template = await PromptRegistry().get(self.name, ctx.db)
        prompt = (
            template
            .replace("ARTICLE_TITLE", source.get("title", ""))
            .replace("ARTICLE_BODY", (source.get("body_html", "") or source.get("outline_text", ""))[:2000])
            .replace("KEYWORD", source.get("keyword", ""))
            .replace("LEARNED_PREFERENCES", learned_preferences)
        )

        raw = await self.call_llm(ctx, prompt)
        post_data = _parse_post(raw)

        post_id = str(uuid.uuid4())
        hashtags = post_data.get("hashtags", [])
        content = post_data.get("content", raw.strip()[:3000])

        await ctx.db.execute(
            text(
                "INSERT INTO linkedin_posts "
                "  (id, org_id, article_id, content, hashtags, status, created_at) "
                "VALUES "
                "  (CAST(:id AS uuid), :org_id, CAST(:article_id AS uuid), "
                "   :content, :hashtags, 'draft', now())"
            ),
            {
                "id": post_id,
                "org_id": ctx.org_id,
                "article_id": article_id,
                "content": content,
                "hashtags": hashtags,
            },
        )
        await ctx.db.flush()

        output = LinkedInAgentOutput(
            linkedin_post_id=post_id,
            article_id=article_id,
            word_count=len(content.split()),
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
    return {
        "id": str(row[0]),
        "keyword": row[1] or "",
        "title": row[2] or "",
        "body_html": row[3] or "",
    }


async def _load_plan(plan_id: str, org_id: str, db) -> dict | None:
    """Load article plan — outline text used instead of full article body."""
    result = await db.execute(
        text("SELECT id, keyword, title, outline, content_angle FROM article_plans "
             "WHERE id = CAST(:id AS uuid) AND org_id = :org_id"),
        {"id": plan_id, "org_id": org_id},
    )
    row = result.fetchone()
    if not row:
        return None
    outline = row[3] or []
    # Convert outline JSON to readable text for the prompt
    outline_text = "\n".join(
        f"- {s.get('h2', '')}: {s.get('detail', '')}"
        for s in (outline if isinstance(outline, list) else [])
    )
    return {
        "id": str(row[0]),
        "keyword": row[1] or "",
        "title": row[2] or "",
        "outline_text": outline_text,
        "body_html": "",  # no full body — using outline only
    }


def _parse_post(raw: str) -> dict:
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```")
        return json.loads(clean)
    except Exception:
        return {"content": raw.strip()[:3000], "hashtags": []}
