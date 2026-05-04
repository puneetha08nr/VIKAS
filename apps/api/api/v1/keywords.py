import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy import String, cast, select, text
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

import agents.seo.keyword_research  # noqa: F401 — ensure @register has run
import agents.seo.keyword_validator  # noqa: F401 — ensure @register has run
from api.deps import get_current_org, get_db_for_org
from core.task_queue import AgentCommand, dispatch
from db.models.agent_runs import AgentRun, AgentRunStatus
from db.models.keywords import Keyword, KeywordStatus
from db.models.organizations import Organization

router = APIRouter(prefix="/keywords", tags=["keywords"])


class ResearchBody(BaseModel):
    seed_keyword: str


class ValidateBody(BaseModel):
    keyword_ids: list[str]


# ── List / stats ──────────────────────────────────────────────────────────────

@router.get("")
async def list_keywords(
    kw_status: KeywordStatus | None = Query(None, alias="status"),
    intent: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    q = select(Keyword).order_by(Keyword.volume.desc().nullslast()).limit(limit)
    if kw_status:
        q = q.where(cast(Keyword.status, String) == kw_status.value)
    if intent:
        q = q.where(Keyword.intent == intent)
    result = await db.execute(q)
    return [_kw_dict(k) for k in result.scalars().all()]


@router.get("/stats")
async def keyword_stats(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    # Cast status::text to avoid the missing text=keyword_status operator in PostgreSQL
    result = await db.execute(
        text("""
            SELECT
                COUNT(*)                                                  AS total,
                COUNT(*) FILTER (WHERE status::text = 'raw')             AS raw,
                COUNT(*) FILTER (WHERE status::text = 'validated')       AS validated,
                COUNT(*) FILTER (WHERE status::text = 'archived')        AS archived,
                COUNT(*) FILTER (WHERE status::text = 'clustered')       AS clustered,
                COUNT(*) FILTER (WHERE intent = 'commercial')            AS commercial,
                COUNT(*) FILTER (WHERE intent = 'informational')         AS informational
            FROM keywords
        """)
    )
    row = result.mappings().one()
    return {
        "total": row["total"],
        "raw": row["raw"],
        "validated": row["validated"],
        "archived": row["archived"],
        "clustered": row["clustered"],
        "commercial": row["commercial"],
        "informational": row["informational"],
    }


# ── Agent dispatch ────────────────────────────────────────────────────────────

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
    return await _dispatch_or_fail(command, run, db)


@router.post("/validate-all", status_code=http_status.HTTP_202_ACCEPTED)
async def run_validate_all(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    result = await db.execute(
        select(Keyword.id).where(cast(Keyword.status, String) == KeywordStatus.raw.value)
    )
    raw_ids = [str(row.id) for row in result.all()]
    if not raw_ids:
        return {"run_id": None, "keyword_count": 0}

    run = AgentRun(
        org_id=org.id,
        agent_name="keyword_validator",
        status=AgentRunStatus.running,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    command = AgentCommand(
        agent_name="keyword_validator",
        org_id=str(org.id),
        run_id=str(run.id),
        params={"keyword_ids": raw_ids},
    )
    result_dict = await _dispatch_or_fail(command, run, db)
    return {**result_dict, "keyword_count": len(raw_ids)}


@router.post("/validate", status_code=http_status.HTTP_202_ACCEPTED)
async def run_validate(
    body: ValidateBody,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    if not body.keyword_ids:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="keyword_ids must not be empty.",
        )

    run = AgentRun(
        org_id=org.id,
        agent_name="keyword_validator",
        status=AgentRunStatus.running,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    command = AgentCommand(
        agent_name="keyword_validator",
        org_id=str(org.id),
        run_id=str(run.id),
        params={"keyword_ids": body.keyword_ids},
    )
    return await _dispatch_or_fail(command, run, db)


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{keyword_id}/detail")
async def keyword_detail(
    keyword_id: str,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    try:
        kw_uuid = uuid.UUID(keyword_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Keyword not found")

    result = await db.execute(select(Keyword).where(Keyword.id == kw_uuid))
    kw = result.scalar_one_or_none()
    if kw is None:
        raise HTTPException(status_code=404, detail="Keyword not found")

    # Recent agent runs for this keyword (by proximity to creation time, last 5)
    runs_result = await db.execute(
        select(AgentRun)
        .where(
            AgentRun.agent_name.in_(["keyword_research", "keyword_validator"]),
            AgentRun.started_at >= kw.created_at,
        )
        .order_by(AgentRun.started_at.desc())
        .limit(5)
    )
    recent_runs = [_run_dict(r) for r in runs_result.scalars().all()]

    return {
        **_kw_dict(kw),
        "recent_runs": recent_runs,
        "content_count": 0,       # placeholder until content pipeline exists
        "trend_data": [0] * 12,   # placeholder until GSC integration
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _dispatch_or_fail(
    command: AgentCommand, run: AgentRun, db: AsyncSession
) -> dict:
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
        "data_source": k.data_source,
        "source_agent": k.source_agent,
        "source_run_id": str(k.source_run_id) if k.source_run_id else None,
        "cluster_id": str(k.cluster_id) if k.cluster_id else None,
        "created_at": k.created_at.isoformat() if k.created_at else None,
    }


def _run_dict(r: AgentRun) -> dict:
    return {
        "run_id": str(r.id),
        "agent_name": r.agent_name,
        "status": r.status,
        "duration_ms": r.duration_ms,
        "tokens_in": r.tokens_in,
        "tokens_out": r.tokens_out,
        "cost_usd": r.cost_usd,
        "model_used": r.model_used,
        "error": r.error,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
    }
