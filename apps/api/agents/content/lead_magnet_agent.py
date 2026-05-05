"""lead_magnet_agent — generates a lead magnet from a keyword.

Standard tier LLM. Writes to lead_magnets table.

Input params:
  keyword (str, required)
  format  (str, optional — checklist | ebook | template, default: checklist)
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import LeadMagnetAgentOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

VALID_FORMATS = {"checklist", "ebook", "template"}


@register
class LeadMagnetAgent(BaseAgent):
    name = "lead_magnet_agent"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        keyword = str(ctx.params.get("keyword", "")).strip()
        if not keyword:
            return AgentResult(status="failed", error="keyword param is required")

        fmt = str(ctx.params.get("format", "checklist")).strip().lower()
        if fmt not in VALID_FORMATS:
            fmt = "checklist"

        template = await PromptRegistry().get(self.name, ctx.db)
        prompt = (
            template
            .replace("KEYWORD", keyword)
            .replace("FORMAT", fmt)
        )

        raw = await self.call_llm(ctx, prompt)
        lead_magnet = _parse_lead_magnet(raw, keyword, fmt)

        lm_id = str(uuid.uuid4())
        await ctx.db.execute(
            text(
                "INSERT INTO lead_magnets "
                "  (id, org_id, keyword, format, title, body, status, created_at) "
                "VALUES "
                "  (CAST(:id AS uuid), :org_id, :keyword, :format, :title, :body, 'draft', now())"
            ),
            {
                "id": lm_id,
                "org_id": ctx.org_id,
                "keyword": keyword,
                "format": fmt,
                "title": lead_magnet.get("title", f"{keyword} {fmt}"),
                "body": lead_magnet.get("body", raw.strip()),
            },
        )
        await ctx.db.flush()

        output = LeadMagnetAgentOutput(
            lead_magnet_id=lm_id,
            keyword=keyword,
            format=fmt,
            title=lead_magnet.get("title", f"{keyword} {fmt}"),
            status="draft",
        )
        return AgentResult(status="success", data=output.model_dump())


def _parse_lead_magnet(raw: str, keyword: str, fmt: str) -> dict:
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```")
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"title": f"{keyword.title()} {fmt.title()}", "body": raw.strip()}
