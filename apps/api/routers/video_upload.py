"""Video upload endpoint — public, token-authenticated.

The upload_token is the only credential — no JWT required.
External video team workflow:
  1. GET  /api/video-upload/{token}  → receive job brief (title, script, scenes)
  2. POST /api/video-upload/{token}  → submit finished MP4

After a successful POST the job transitions to video_ready, completed_at is
recorded, and a confirmation email is sent back to VIDEO_TEAM_EMAIL.
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path

import anyio
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from db.session import AdminSessionLocal
from integrations.email import EmailIntegration

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video-upload", tags=["video-upload"])

_UPLOAD_DIR = Path("uploads/videos")
_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB


# ── Dependency ────────────────────────────────────────────────────────────────

async def _admin_db():
    """Admin session that bypasses RLS — upload_token lookup requires no org context."""
    async with AdminSessionLocal() as session:
        yield session


# ── GET — job brief ───────────────────────────────────────────────────────────

@router.get("/{upload_token}")
async def get_video_brief(
    upload_token: str,
    db: AsyncSession = Depends(_admin_db),
) -> dict:
    """Return job brief for the video team. No auth — token is the credential."""
    job = await _fetch_job(upload_token, db)
    return {
        "job_id": str(job["id"]),
        "title": job["title"],
        "script_text": job["script_text"],
        "scenes": job["scenes"],
        "brand_voice": job["brand_voice"],
        "broll_suggestions": job["broll_suggestions"],
        "status": job["status"],
        "created_at": job["created_at"].isoformat() if job["created_at"] else None,
    }


# ── POST — submit finished video ──────────────────────────────────────────────

@router.post("/{upload_token}", status_code=status.HTTP_200_OK)
async def submit_video(
    upload_token: str,
    video_file: UploadFile = File(..., description="Finished video file (MP4)"),
    notes: str | None = Form(None),
    db: AsyncSession = Depends(_admin_db),
) -> dict:
    """Accept the finished video from the external team."""
    job = await _fetch_job(upload_token, db)

    if job["status"] not in ("pending_video", "in_review"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is in status '{job['status']}' — cannot accept upload.",
        )

    if video_file.content_type not in ("video/mp4", "video/mpeg"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Only MP4 video files are accepted.",
        )

    job_id = str(job["id"])
    title = job["title"] or ""

    # Save file
    video_path = await _save_upload(video_file, job_id)
    video_url = f"/uploads/videos/{video_path.name}"

    now = datetime.now(UTC)
    await db.execute(
        text(
            "UPDATE video_jobs SET "
            "  status = 'video_ready', "
            "  video_url = :video_url, "
            "  notes = :notes, "
            "  completed_at = :completed_at, "
            "  updated_at = :updated_at "
            "WHERE id = CAST(:job_id AS uuid)"
        ),
        {
            "job_id": job_id,
            "video_url": video_url,
            "notes": notes,
            "completed_at": now,
            "updated_at": now,
        },
    )
    await db.commit()
    logger.info("video_upload: job %s → video_ready", job_id)

    # Confirmation email
    await _send_confirmation_email(title)

    return {"status": "uploaded", "job_id": job_id}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch_job(upload_token: str, db: AsyncSession) -> dict:
    try:
        token_uuid = uuid.UUID(upload_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    result = await db.execute(
        text(
            "SELECT id, org_id, title, script_text, scenes, broll_suggestions, "
            "       brand_voice, status, created_at "
            "FROM video_jobs WHERE upload_token = CAST(:token AS uuid)"
        ),
        {"token": str(token_uuid)},
    )
    row = result.mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return dict(row)


async def _save_upload(video: UploadFile, job_id: str) -> Path:
    await anyio.Path(_UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    suffix = Path(video.filename or "video.mp4").suffix or ".mp4"
    dest = _UPLOAD_DIR / f"{job_id}{suffix}"
    content = await video.read()
    if len(content) > _MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File exceeds 2 GB limit.",
        )
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, dest.write_bytes, content)
    return dest


async def _send_confirmation_email(title: str) -> None:
    body_html = (
        "<p>We received your video. "
        "It will be reviewed and published shortly.</p>"
    )
    email = EmailIntegration(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
    )
    await email.send_email(
        to=settings.video_team_email,
        subject=f"Upload received — {title}",
        body_html=body_html,
    )
