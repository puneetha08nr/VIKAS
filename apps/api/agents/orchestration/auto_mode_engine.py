"""auto_mode_engine — nightly orchestrator that selects top opportunities and triggers pipelines.

Fast tier (no LLM generation — selection logic only).
Reads top-N opportunities by composite_score, dispatches pipeline_orchestrator for each.

Input params:
  max_pipelines (int, optional — max opportunities to process, default: 5)
  dry_run       (bool, optional — if true, select but do not dispatch, default: false)
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import REGISTRY, register
from core.contracts import AutoModeEngineOutput

logger = logging.getLogger(__name__)


@register
class AutoModeEngineAgent(BaseAgent):
    name = "auto_mode_engine"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        max_pipelines = int(ctx.params.get("max_pipelines", 5))
        if max_pipelines < 1:
            max_pipelines = 5

        dry_run = bool(ctx.params.get("dry_run", False))

        opportunities = await _select_opportunities(ctx.org_id, max_pipelines, ctx.db)

        if dry_run:
            output = AutoModeEngineOutput(
                opportunities_selected=len(opportunities),
                pipelines_triggered=0,
                status="success",
            )
            return AgentResult(status="success", data=output.model_dump())

        triggered = 0
        for opp in opportunities:
            result = await _run_pipeline(ctx, opp["opportunity_id"])
            if result.status != "failed":
                triggered += 1
            else:
                logger.warning(
                    "auto_mode_engine: pipeline failed for opp %s: %s",
                    opp["opportunity_id"],
                    result.error,
                )

        output = AutoModeEngineOutput(
            opportunities_selected=len(opportunities),
            pipelines_triggered=triggered,
            status="success",
        )
        return AgentResult(status="success", data=output.model_dump())


async def _select_opportunities(org_id: str, limit: int, db) -> list[dict]:
    try:
        result = await db.execute(
            text(
                "SELECT id, composite_score FROM opportunities "
                "WHERE org_id = :org_id AND status = 'open' "
                "ORDER BY composite_score DESC "
                "LIMIT :limit"
            ),
            {"org_id": org_id, "limit": limit},
        )
        rows = result.fetchall()
        return [
            {"opportunity_id": str(row[0]), "composite_score": float(row[1] or 0)}
            for row in rows
        ]
    except Exception:
        logger.warning("auto_mode_engine: failed to load opportunities")
        return []


async def _run_pipeline(ctx: AgentContext, opportunity_id: str) -> AgentResult:
    if "pipeline_orchestrator" not in REGISTRY:
        return AgentResult(status="failed", error="pipeline_orchestrator not registered")
    sub_ctx = AgentContext(
        org_id=ctx.org_id,
        run_id=ctx.run_id,
        params={"opportunity_id": opportunity_id},
        config=ctx.config,
        db=ctx.db,
        llm=ctx.llm,
    )
    try:
        return await REGISTRY["pipeline_orchestrator"]().execute(sub_ctx)
    except Exception as exc:
        logger.exception(
            "auto_mode_engine: pipeline_orchestrator raised for opp %s",
            opportunity_id,
        )
        return AgentResult(status="failed", error=str(exc))
