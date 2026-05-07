import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

# Import agent modules to ensure @register decorators have run before any
# call to agent_registry.list_agents() — add new agents here as they are built.
import agents.seo.keyword_research  # noqa: F401
import agents.seo.keyword_validator  # noqa: F401
import agents.seo.opportunity_scorer  # noqa: F401
import agents.seo.trend_collector  # noqa: F401
import agents.seo.gap_analyzer  # noqa: F401
import agents.seo.rank_tracker  # noqa: F401
import agents.seo.site_auditor  # noqa: F401
import agents.competitor.competitor_monitor  # noqa: F401
import agents.competitor.content_extractor  # noqa: F401
import agents.competitor.keyword_overlap_analyzer  # noqa: F401
import agents.knowledge.brand_voice_keeper  # noqa: F401
import agents.content.content_director  # noqa: F401
import agents.content.article_planner  # noqa: F401
import agents.content.article_writer  # noqa: F401
import agents.content.linkedin_agent  # noqa: F401
import agents.content.twitter_agent  # noqa: F401
import agents.content.newsletter_agent  # noqa: F401
import agents.content.video_script_agent  # noqa: F401
import agents.content.lead_magnet_agent  # noqa: F401
import agents.content.image_creator_agent  # noqa: F401
from api.deps import get_current_org, get_db_for_org
from core import agent_registry
from core.task_queue import AgentCommand, dispatch
from db.models.agent_runs import AgentRun, AgentRunStatus
from db.models.organizations import Organization

router = APIRouter(prefix="/agents", tags=["agents"])


class RunAgentBody(BaseModel):
    params: dict = {}


@router.post("/{agent_name}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_agent(
    agent_name: str,
    body: RunAgentBody,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    if agent_name not in agent_registry.list_agents():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_name}' not found. Available: {agent_registry.list_agents()}",
        )

    run = AgentRun(
        org_id=org.id,
        agent_name=agent_name,
        status=AgentRunStatus.running,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    command = AgentCommand(
        agent_name=agent_name,
        org_id=str(org.id),
        run_id=str(run.id),
        params=body.params,
    )

    try:
        dispatch(command)
    except Exception as exc:
        await db.execute(
            sa_update(AgentRun)
            .where(AgentRun.id == run.id)
            .values(
                status=AgentRunStatus.failed,
                error=f"Dispatch failed: {exc}",
                completed_at=datetime.now(UTC),
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Agent queue unavailable — is Redis running? ({exc})",
        )

    return {"run_id": str(run.id)}


@router.get("/runs")
async def list_runs(
    limit: int = Query(50, ge=1, le=200),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    result = await db.execute(
        select(AgentRun).order_by(AgentRun.started_at.desc()).limit(limit)
    )
    runs = result.scalars().all()
    return [_run_summary(r) for r in runs]


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    result = await db.execute(select(AgentRun).where(AgentRun.id == run_uuid))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    return {
        "run_id": str(run.id),
        "agent_name": run.agent_name,
        "status": run.status,
        "duration_ms": run.duration_ms,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "cost_usd": run.cost_usd,
        "model_used": run.model_used,
        "error": run.error,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }


def _run_summary(run: AgentRun) -> dict:
    return {
        "run_id": str(run.id),
        "agent_name": run.agent_name,
        "status": run.status,
        "duration_ms": run.duration_ms,
        "cost_usd": run.cost_usd,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
    }
