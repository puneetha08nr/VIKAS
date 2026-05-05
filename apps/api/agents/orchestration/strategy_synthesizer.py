"""strategy_synthesizer — synthesizes a strategic content plan from top opportunities.

Advanced tier LLM. Reads top-N opportunities from DB, writes to strategy_reports table.

Input params:
  limit (int, optional — max opportunities to analyze, default: 10)
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import StrategySynthesizerOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


@register
class StrategySynthesizerAgent(BaseAgent):
    name = "strategy_synthesizer"
    tier = "advanced"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        limit = int(ctx.params.get("limit", 10))
        if limit < 1:
            limit = 10

        opportunities = await _load_opportunities(ctx.org_id, limit, ctx.db)

        template = await PromptRegistry().get(self.name, ctx.db)
        opp_text = json.dumps(opportunities, indent=2)
        prompt = (
            template
            .replace("OPPORTUNITIES_JSON", opp_text)
            .replace("OPPORTUNITY_COUNT", str(len(opportunities)))
        )

        raw = await self.call_llm(ctx, prompt)
        report = _parse_report(raw)

        report_id = str(uuid.uuid4())
        recommendations = report.get("recommendations", [])
        summary = report.get("summary", raw.strip()[:2000])

        await ctx.db.execute(
            text(
                "INSERT INTO strategy_reports "
                "  (id, org_id, opportunities_analyzed, recommendations, summary, status, created_at) "
                "VALUES "
                "  (CAST(:id AS uuid), :org_id, :opportunities_analyzed, "
                "   CAST(:recommendations AS jsonb), :summary, 'success', now())"
            ),
            {
                "id": report_id,
                "org_id": ctx.org_id,
                "opportunities_analyzed": len(opportunities),
                "recommendations": json.dumps(recommendations),
                "summary": summary,
            },
        )
        await ctx.db.flush()

        output = StrategySynthesizerOutput(
            report_id=report_id,
            opportunities_analyzed=len(opportunities),
            recommendations_count=len(recommendations),
            status="success",
        )
        return AgentResult(status="success", data=output.model_dump())


async def _load_opportunities(org_id: str, limit: int, db) -> list[dict]:
    result = await db.execute(
        text(
            "SELECT o.id, k.keyword, o.composite_score, o.status "
            "FROM opportunities o "
            "JOIN keywords k ON k.id = o.keyword_id "
            "WHERE o.org_id = :org_id AND o.status = 'open' "
            "ORDER BY o.composite_score DESC "
            "LIMIT :limit"
        ),
        {"org_id": org_id, "limit": limit},
    )
    rows = result.fetchall()
    return [
        {
            "opportunity_id": str(row[0]),
            "keyword": row[1] or "",
            "composite_score": float(row[2]) if row[2] is not None else 0.0,
            "status": row[3] or "open",
        }
        for row in rows
    ]


def _parse_report(raw: str) -> dict:
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```")
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {"summary": raw.strip()[:2000], "recommendations": []}
