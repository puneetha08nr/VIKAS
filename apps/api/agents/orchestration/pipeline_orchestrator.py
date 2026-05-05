"""pipeline_orchestrator — runs the full keyword→content pipeline for one opportunity.

Standard tier (minimal LLM). Orchestrates: content_director, wordpress_publisher.
Logs pipeline progress to pipeline_runs table.

Input params:
  opportunity_id (str, required)
  auto_publish   (bool, optional — if true, publish to WordPress after content is created, default: false)
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register, REGISTRY
from core.contracts import PipelineOrchestratorOutput

logger = logging.getLogger(__name__)


@register
class PipelineOrchestratorAgent(BaseAgent):
    name = "pipeline_orchestrator"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        opportunity_id = str(ctx.params.get("opportunity_id", "")).strip()
        if not opportunity_id:
            return AgentResult(status="failed", error="opportunity_id param is required")

        auto_publish = bool(ctx.params.get("auto_publish", False))

        pipeline_run_id = str(uuid.uuid4())
        stages_completed = 0
        stages_failed = 0
        article_id = ""

        # Stage 1: content_director
        cd_result = await _run_sub(ctx, "content_director", {"opportunity_id": opportunity_id})
        if cd_result.status == "failed":
            stages_failed += 1
            logger.warning("pipeline_orchestrator: content_director failed: %s", cd_result.error)
        else:
            stages_completed += 1
            article_id = cd_result.data.get("article_id", "")

        # Stage 2: wordpress_publisher (only if auto_publish and article was created)
        if auto_publish and article_id:
            wp_result = await _run_sub(
                ctx, "wordpress_publisher",
                {"article_id": article_id, "wp_status": "publish"},
            )
            if wp_result.status == "failed":
                stages_failed += 1
                logger.warning("pipeline_orchestrator: wordpress_publisher failed: %s", wp_result.error)
            else:
                stages_completed += 1

        overall_status = "failed" if stages_completed == 0 else (
            "partial" if stages_failed > 0 else "success"
        )

        await ctx.db.execute(
            text(
                "INSERT INTO pipeline_runs "
                "  (id, org_id, pipeline_name, status, started_at, completed_at) "
                "VALUES "
                "  (CAST(:id AS uuid), :org_id, :pipeline_name, :status, now(), now())"
            ),
            {
                "id": pipeline_run_id,
                "org_id": ctx.org_id,
                "pipeline_name": "content_pipeline",
                "status": overall_status,
            },
        )
        await ctx.db.flush()

        output = PipelineOrchestratorOutput(
            opportunity_id=opportunity_id,
            stages_completed=stages_completed,
            stages_failed=stages_failed,
            status=overall_status,
        )
        return AgentResult(status="success", data=output.model_dump())


async def _run_sub(ctx: AgentContext, agent_name: str, params: dict) -> AgentResult:
    if agent_name not in REGISTRY:
        return AgentResult(status="failed", error=f"{agent_name} not registered")
    sub_ctx = AgentContext(
        org_id=ctx.org_id,
        run_id=ctx.run_id,
        params=params,
        config=ctx.config,
        db=ctx.db,
        llm=ctx.llm,
    )
    try:
        return await REGISTRY[agent_name]().execute(sub_ctx)
    except Exception as exc:
        logger.exception("pipeline_orchestrator: sub-agent %s raised", agent_name)
        return AgentResult(status="failed", error=str(exc))
