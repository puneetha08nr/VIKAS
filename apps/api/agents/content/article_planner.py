"""article_planner — generates a structured article plan from an opportunity.

Standard tier LLM.
  1. Reads opportunity + keyword from DB.
  2. Loads brand voice + knowledge chunks for context.
  3. LLM generates: title, meta_description, word_count_target, outline, content_angle, cta.
  4. Writes to article_plans table.

Input params:
  opportunity_id (str, required)
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import ArticlePlannerOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


@register
class ArticlePlannerAgent(BaseAgent):
    name = "article_planner"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        opportunity_id = str(ctx.params.get("opportunity_id", "")).strip()
        if not opportunity_id:
            return AgentResult(status="failed", error="opportunity_id param is required")

        # Load opportunity
        opp = await _load_opportunity(opportunity_id, ctx.org_id, ctx.db)
        if not opp:
            return AgentResult(status="failed", error=f"Opportunity '{opportunity_id}' not found")

        keyword = opp.get("keyword", "")

        # Load brand voice
        bv_result = await ctx.db.execute(
            text("SELECT tone, style_rules FROM brand_voice WHERE org_id = :org_id LIMIT 1"),
            {"org_id": ctx.org_id},
        )
        bv_row = bv_result.fetchone()
        brand_voice = f"Tone: {bv_row[0] or 'professional'}" if bv_row else "Tone: professional"

        # Load relevant knowledge chunks
        chunks_result = await ctx.db.execute(
            text("SELECT chunk_text FROM knowledge_chunks WHERE org_id = :org_id LIMIT 3"),
            {"org_id": ctx.org_id},
        )
        chunks = [row[0] for row in chunks_result.fetchall()]
        knowledge_context = "\n---\n".join(chunks) if chunks else "No knowledge base entries."

        # Load and fill prompt
        template = await PromptRegistry().get(self.name, ctx.db)
        prompt = (
            template
            .replace("KEYWORD", keyword)
            .replace("BRAND_VOICE", brand_voice)
            .replace("KNOWLEDGE_CHUNKS", knowledge_context[:2000])
        )

        raw = await self.call_llm(ctx, prompt)
        plan = _parse_plan(raw)

        plan_id = str(uuid.uuid4())
        await ctx.db.execute(
            text(
                "INSERT INTO article_plans "
                "  (id, org_id, opportunity_id, keyword, title, meta_description, "
                "   outline, word_count_target, content_angle, cta, "
                "   status, created_at, updated_at) "
                "VALUES "
                "  (CAST(:id AS uuid), :org_id, CAST(:opp_id AS uuid), :keyword, :title, "
                "   :meta_desc, CAST(:outline AS jsonb), :word_count, :angle, :cta, "
                "   'planned', now(), now())"
            ),
            {
                "id": plan_id,
                "org_id": ctx.org_id,
                "opp_id": opportunity_id,
                "keyword": keyword,
                "title": plan.get("title", keyword),
                "meta_desc": plan.get("meta_description", ""),
                "outline": json.dumps(plan.get("outline", [])),
                "word_count": int(plan.get("word_count_target", 1800)),
                "angle": plan.get("content_angle", ""),
                "cta": plan.get("cta", ""),
            },
        )
        await ctx.db.flush()

        output = ArticlePlannerOutput(
            article_plan_id=plan_id,
            keyword=keyword,
            title=plan.get("title", keyword),
            meta_description=plan.get("meta_description", ""),
            word_count_target=int(plan.get("word_count_target", 1800)),
            outline_sections=len(plan.get("outline", [])),
            status="planned",
        )
        return AgentResult(status="success", data=output.model_dump())


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _load_opportunity(opportunity_id: str, org_id: str, db) -> dict | None:
    result = await db.execute(
        text(
            "SELECT o.id, k.keyword "
            "FROM opportunities o "
            "JOIN keywords k ON k.id = o.keyword_id "
            "WHERE o.id = CAST(:opp_id AS uuid) AND o.org_id = :org_id"
        ),
        {"opp_id": opportunity_id, "org_id": org_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "keyword": row[1] or ""}


def _parse_plan(raw: str) -> dict:
    try:
        clean = raw.strip()
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        return json.loads(clean)
    except Exception:
        return {
            "title": "",
            "meta_description": "",
            "word_count_target": 1800,
            "outline": [],
            "content_angle": "",
            "cta": "",
        }
