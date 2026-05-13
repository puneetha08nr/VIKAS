"""article_writer — writes a full article from an article plan.

Standard tier LLM.
  1. Reads article plan from article_plans table.
  2. Loads brand voice + knowledge chunks + internal link suggestions.
  3. LLM writes each H2 section separately.
  4. Assembles full HTML article.
  5. Writes to articles table.
  6. Updates article_plans.status = 'written'.

Input params:
  article_plan_id (str, required)
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import ArticleWriterOutput
from core.preference_loader import load_preferences
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


@register
class ArticleWriterAgent(BaseAgent):
    name = "article_writer"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        plan_id = str(ctx.params.get("article_plan_id", "")).strip()
        if not plan_id:
            return AgentResult(status="failed", error="article_plan_id param is required")

        plan = await _load_plan(plan_id, ctx.org_id, ctx.db)
        if not plan:
            return AgentResult(status="failed", error=f"Article plan '{plan_id}' not found")

        title = plan.get("title", "")
        keyword = plan.get("keyword", "")
        outline = plan.get("outline", [])
        word_count_target = plan.get("word_count_target", 1800)

        # Load brand voice
        bv_result = await ctx.db.execute(
            text("SELECT tone FROM brand_voice WHERE org_id = :org_id LIMIT 1"),
            {"org_id": ctx.org_id},
        )
        bv_row = bv_result.fetchone()
        brand_voice = f"Tone: {bv_row[0] or 'professional'}" if bv_row else "Tone: professional"

        # Load knowledge chunks
        chunks_result = await ctx.db.execute(
            text("SELECT chunk_text FROM knowledge_chunks WHERE org_id = :org_id LIMIT 5"),
            {"org_id": ctx.org_id},
        )
        knowledge_chunks = "\n---\n".join(row[0] for row in chunks_result.fetchall()) or "None."

        # Load learned preferences from human feedback
        learned_preferences = await load_preferences(ctx.org_id, "article", ctx.db)

        template = await PromptRegistry().get(self.name, ctx.db)

        # Write each section
        sections_html: list[str] = []
        per_section_words = max(200, word_count_target // max(len(outline), 1))

        for section in outline:
            h2 = section.get("h2", "")
            if not h2:
                continue
            h3s = section.get("h3s", [])
            outline_detail = f"H2: {h2}\nH3s: {', '.join(h3s)}"

            prompt = (
                template
                .replace("SECTION_TITLE", h2)
                .replace("ARTICLE_TITLE", title)
                .replace("KEYWORD", keyword)
                .replace("BRAND_VOICE", brand_voice)
                .replace("SECTION_OUTLINE", outline_detail)
                .replace("KNOWLEDGE_CHUNKS", knowledge_chunks[:1000])
                .replace("INTERNAL_LINKS", "")
                .replace("WORD_COUNT", str(per_section_words))
                .replace("LEARNED_PREFERENCES", learned_preferences)
            )

            section_html = await self.call_llm(ctx, prompt)
            sections_html.append(f"<h2>{h2}</h2>\n{section_html.strip()}")

        if not sections_html:
            # Fallback: write whole article in one shot
            prompt = (
                template
                .replace("SECTION_TITLE", "Introduction")
                .replace("ARTICLE_TITLE", title)
                .replace("KEYWORD", keyword)
                .replace("BRAND_VOICE", brand_voice)
                .replace("SECTION_OUTLINE", title)
                .replace("KNOWLEDGE_CHUNKS", knowledge_chunks[:1000])
                .replace("INTERNAL_LINKS", "")
                .replace("WORD_COUNT", str(word_count_target))
                .replace("LEARNED_PREFERENCES", learned_preferences)
            )
            content = await self.call_llm(ctx, prompt)
            sections_html.append(content.strip())

        body_html = "\n\n".join(sections_html)
        word_count = len(body_html.split())

        article_id = str(uuid.uuid4())
        await ctx.db.execute(
            text(
                "INSERT INTO articles "
                "  (id, org_id, article_plan_id, keyword, title, body_html, "
                "   word_count, status, created_at, updated_at) "
                "VALUES "
                "  (CAST(:id AS uuid), :org_id, CAST(:plan_id AS uuid), "
                "   :keyword, :title, :body_html, :word_count, 'draft', now(), now())"
            ),
            {
                "id": article_id,
                "org_id": ctx.org_id,
                "plan_id": plan_id,
                "keyword": keyword,
                "title": title,
                "body_html": body_html,
                "word_count": word_count,
            },
        )

        await ctx.db.execute(
            text("UPDATE article_plans SET status = 'written', updated_at = now() "
                 "WHERE id = CAST(:plan_id AS uuid)"),
            {"plan_id": plan_id},
        )

        await ctx.db.flush()

        output = ArticleWriterOutput(
            article_id=article_id,
            article_plan_id=plan_id,
            title=title,
            word_count=word_count,
            sections_written=len(sections_html),
            status="draft",
        )
        return AgentResult(status="success", data=output.model_dump())


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _load_plan(plan_id: str, org_id: str, db) -> dict | None:
    result = await db.execute(
        text(
            "SELECT id, keyword, title, outline, word_count_target "
            "FROM article_plans "
            "WHERE id = CAST(:plan_id AS uuid) AND org_id = :org_id"
        ),
        {"plan_id": plan_id, "org_id": org_id},
    )
    row = result.fetchone()
    if not row:
        return None
    outline = row[3] if isinstance(row[3], list) else []
    return {
        "id": str(row[0]),
        "keyword": row[1] or "",
        "title": row[2] or "",
        "outline": outline,
        "word_count_target": row[4] or 1800,
    }
