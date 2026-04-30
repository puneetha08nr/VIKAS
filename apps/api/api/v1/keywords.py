import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

import agents.seo.keyword_research  # noqa: F401 — ensure @register has run

from api.deps import get_current_org, get_db_for_org
from core.task_queue import AgentCommand, dispatch
from db.models.agent_runs import AgentRun, AgentRunStatus
from db.models.keywords import Keyword, KeywordStatus
from db.models.organizations import Organization

router = APIRouter(prefix="/keywords", tags=["keywords"])


class ResearchBody(BaseModel):
    seed_keyword: str


@router.get("")
async def list_keywords(
    kw_status: KeywordStatus | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    q = select(Keyword).order_by(Keyword.volume.desc().nullslast()).limit(limit)
    if kw_status:
        q = q.where(Keyword.status == kw_status)
    result = await db.execute(q)
    return [_kw_dict(k) for k in result.scalars().all()]


@router.get("/stats")
async def keyword_stats(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    result = await db.execute(
        select(
            func.count().label("total"),
            func.count().filter(Keyword.status == KeywordStatus.raw).label("raw"),
            func.count().filter(Keyword.status == KeywordStatus.validated).label("validated"),
            func.count().filter(Keyword.status == KeywordStatus.archived).label("archived"),
            func.count().filter(Keyword.intent == "commercial").label("commercial"),
            func.count().filter(Keyword.intent == "informational").label("informational"),
        ).select_from(Keyword)
    )
    row = result.one()
    return {
        "total": row.total,
        "raw": row.raw,
        "validated": row.validated,
        "archived": row.archived,
        "commercial": row.commercial,
        "informational": row.informational,
    }


@router.post("/research", status_code=http_status.HTTP_202_ACCEPTED)
async def run_keyword_research(
    body: ResearchBody,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    run = AgentRun(
        org_id=org.id,
        agent_name="keyword_research",
        status=AgentRunStatus.running,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    command = AgentCommand(
        agent_name="keyword_research",
        org_id=str(org.id),
        run_id=str(run.id),
        params={"seed_keyword": body.seed_keyword},
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
                completed_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Agent queue unavailable — is Redis running? ({exc})",
        )

    return {"run_id": str(run.id)}


def _kw_dict(k: Keyword) -> dict:
    return {
        "id": str(k.id),
        "keyword": k.keyword,
        "volume": k.volume,
        "kd": k.kd,
        "cpc": k.cpc,
        "intent": k.intent,
        "reason": k.reason,
        "status": k.status,
        "source_agent": k.source_agent,
        "created_at": k.created_at,
    }
