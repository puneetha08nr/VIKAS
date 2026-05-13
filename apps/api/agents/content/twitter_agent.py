"""twitter_agent — generates a Twitter/X thread from an article.

Standard tier LLM. Writes to twitter_threads table.

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
from core.contracts import TwitterAgentOutput
from core.preference_loader import load_preferences
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


@register
class TwitterAgent(BaseAgent):
    name = "twitter_agent"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        article_id = str(ctx.params.get("article_id", "")).strip()
        article_plan_id = str(ctx.params.get("article_plan_id", "")).strip()

        if not article_id and not article_plan_id:
            return AgentResult(status="failed", error="article_id or article_plan_id param is required")

        # Prefer plan (cheaper) over full article
        if article_plan_id:
            source = await _load_plan(article_plan_id, ctx.org_id, ctx.db)
            if not source:
                return AgentResult(status="failed", error=f"Article plan '{article_plan_id}' not found")
            article_id = article_plan_id
        else:
            source = await _load_article(article_id, ctx.org_id, ctx.db)
            if not source:
                return AgentResult(status="failed", error=f"Article '{article_id}' not found")

        learned_preferences = await load_preferences(ctx.org_id, "twitter", ctx.db)
        template = await PromptRegistry().get(self.name, ctx.db)
        prompt = (
            template
            .replace("ARTICLE_TITLE", source.get("title", ""))
            .replace("ARTICLE_BODY", (source.get("body_html", "") or source.get("outline_text", ""))[:2000])
            .replace("KEYWORD", source.get("keyword", ""))
            .replace("LEARNED_PREFERENCES", learned_preferences)
        )

        raw = await self.call_llm(ctx, prompt)
        tweets = _parse_tweets(raw)

        thread_id = str(uuid.uuid4())
        await ctx.db.execute(
            text(
                "INSERT INTO twitter_threads "
                "  (id, org_id, article_id, tweets, status, created_at) "
                "VALUES "
                "  (CAST(:id AS uuid), :org_id, CAST(:article_id AS uuid), "
                "   CAST(:tweets AS jsonb), 'draft', now())"
            ),
            {
                "id": thread_id,
                "org_id": ctx.org_id,
                "article_id": article_id,
                "tweets": json.dumps(tweets),
            },
        )
        await ctx.db.flush()

        output = TwitterAgentOutput(
            twitter_thread_id=thread_id,
            article_id=article_id,
            tweet_count=len(tweets),
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
    """Load article plan outline — used instead of full article to save tokens."""
    result = await db.execute(
        text("SELECT id, keyword, title, outline FROM article_plans "
             "WHERE id = CAST(:id AS uuid) AND org_id = :org_id"),
        {"id": plan_id, "org_id": org_id},
    )
    row = result.fetchone()
    if not row:
        return None
    outline = row[3] or []
    outline_text = "\n".join(
        f"- {s.get('h2', '')}: {s.get('detail', '')}"
        for s in (outline if isinstance(outline, list) else [])
    )
    return {
        "id": str(row[0]),
        "keyword": row[1] or "",
        "title": row[2] or "",
        "outline_text": outline_text,
        "body_html": "",
    }


def _parse_tweets(raw: str) -> list[str]:
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```")
        parsed = json.loads(clean)
        if isinstance(parsed, list):
            return [str(t.get("text", t) if isinstance(t, dict) else t) for t in parsed]
    except Exception:
        pass
    # Fallback: split by newlines, treat each non-empty line as a tweet
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return lines[:8] if lines else [raw.strip()[:280]]
