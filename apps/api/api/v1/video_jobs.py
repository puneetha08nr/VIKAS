"""Internal video jobs API — auth-protected, org-scoped.

Used by the dashboard to review, approve, and track video production.

GET  /api/v1/video-jobs             — list jobs (filterable by status)
GET  /api/v1/video-jobs/{job_id}    — full detail
PUT  /api/v1/video-jobs/{job_id}    — update status / notes
POST /api/v1/video-jobs/dispatch    — trigger video_handoff agent
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_org, get_db_for_org
from core.task_queue import AgentCommand, dispatch
from db.models.agent_runs import AgentRun, AgentRunStatus
from db.models.organizations import Organization
from db.models.video_jobs import VideoJob

router = APIRouter(prefix="/video-jobs", tags=["video-jobs"])

_VALID_STATUSES = {"pending_video", "in_review", "video_ready", "published", "rejected"}


class UpdateJobBody(BaseModel):
    status: str | None = None
    notes: str | None = None
    thumbnail_url: str | None = None


class DispatchBody(BaseModel):
    title: str
    script_text: str
    scenes: list[dict] = []
    broll_suggestions: list = []
    brand_voice: dict = {}
    deadline: str = ""


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("")
async def list_video_jobs(
    job_status: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    q = select(VideoJob).order_by(VideoJob.created_at.desc()).limit(limit)
    if job_status:
        if job_status not in _VALID_STATUSES:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status '{job_status}'. Valid: {sorted(_VALID_STATUSES)}",
            )
        q = q.where(VideoJob.status == job_status)
    result = await db.execute(q)
    return [_job_summary(j) for j in result.scalars().all()]


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{job_id}")
async def get_video_job(
    job_id: str,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    job = await _get_or_404(job_id, db)
    return _job_detail(job)


# ── Update ────────────────────────────────────────────────────────────────────

@router.put("/{job_id}")
async def update_video_job(
    job_id: str,
    body: UpdateJobBody,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    job = await _get_or_404(job_id, db)

    if body.status and body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid status '{body.status}'. Valid: {sorted(_VALID_STATUSES)}",
        )

    updates: dict = {"updated_at": datetime.now(UTC)}
    if body.status is not None:
        updates["status"] = body.status
    if body.notes is not None:
        updates["notes"] = body.notes
    if body.thumbnail_url is not None:
        updates["thumbnail_url"] = body.thumbnail_url

    await db.execute(
        sa_update(VideoJob).where(VideoJob.id == job.id).values(**updates)
    )
    await db.commit()
    await db.refresh(job)
    return _job_detail(job)


# ── Dispatch agent ────────────────────────────────────────────────────────────

@router.post("/dispatch", status_code=http_status.HTTP_202_ACCEPTED)
async def dispatch_video_handoff(
    body: DispatchBody,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    """Enqueue a video_handoff agent run for the given script."""
    run = AgentRun(
        org_id=org.id,
        agent_name="video_handoff",
        status=AgentRunStatus.running,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    command = AgentCommand(
        agent_name="video_handoff",
        org_id=str(org.id),
        run_id=str(run.id),
        params=body.model_dump(),
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
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Agent queue unavailable — is Redis running? ({exc})",
        )
    return {"run_id": str(run.id)}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(job_id: str, db: AsyncSession) -> VideoJob:
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Job not found")
    result = await db.execute(select(VideoJob).where(VideoJob.id == job_uuid))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _job_summary(j: VideoJob) -> dict:
    return {
        "id": str(j.id),
        "title": j.title,
        "status": j.status,
        "notified_at": j.notified_at.isoformat() if j.notified_at else None,
        "completed_at": j.completed_at.isoformat() if j.completed_at else None,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }


def _job_detail(j: VideoJob) -> dict:
    return {
        **_job_summary(j),
        "script_text": j.script_text,
        "scenes": j.scenes,
        "broll_suggestions": j.broll_suggestions,
        "brand_voice": j.brand_voice,
        "video_url": j.video_url,
        "thumbnail_url": j.thumbnail_url,
        "duration_seconds": j.duration_seconds,
        "notes": j.notes,
        "upload_token": str(j.upload_token),
        "updated_at": j.updated_at.isoformat() if j.updated_at else None,
    }
