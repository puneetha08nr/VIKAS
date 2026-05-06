"""Video upload endpoint — public, token-authenticated.

The upload_token is the only credential. No JWT required.
External video team:
  1. Calls GET /api/v1/video-upload/{token} to fetch the brief.
  2. Calls POST /api/v1/video-upload/{token} with the finished video file.

After a successful POST, job status transitions to video_ready and
the completed_at timestamp is recorded.
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

from api.deps import get_admin_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/video-upload", tags=["video-upload"])

_UPLOAD_DIR = Path("uploads/videos")
_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GB hard stop


# ── GET — fetch job brief ─────────────────────────────────────────────────────

@router.get("/{upload_token}")
async def get_video_brief(
    upload_token: str,
    db: AsyncSession = Depends(get_admin_db),
) -> dict:
    """Return job brief for the video team (no auth required, token is credential)."""
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
    video: UploadFile = File(..., description="Finished video file (MP4 preferred)"),
    thumbnail_url: str | None = Form(None),
    duration_seconds: int | None = Form(None),
    notes: str | None = Form(None),
    db: AsyncSession = Depends(get_admin_db),
) -> dict:
    """Accept the finished video upload from the external team."""
    job = await _fetch_job(upload_token, db)

    if job["status"] != "pending_video":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is already in status '{job['status']}' — cannot accept upload.",
        )

    job_id = str(job["id"])

    # Save the file
    video_path = await _save_upload(video, job_id)
    video_url = f"/uploads/videos/{video_path.name}"

    now = datetime.now(UTC)
    await db.execute(
        text(
            "UPDATE video_jobs SET "
            "  status = 'video_ready', "
            "  video_url = :video_url, "
            "  thumbnail_url = :thumbnail_url, "
            "  duration_seconds = :duration_seconds, "
            "  notes = :notes, "
            "  completed_at = :completed_at, "
            "  updated_at = :updated_at "
            "WHERE id = CAST(:job_id AS uuid)"
        ),
        {
            "job_id": job_id,
            "video_url": video_url,
            "thumbnail_url": thumbnail_url,
            "duration_seconds": duration_seconds,
            "notes": notes,
            "completed_at": now,
            "updated_at": now,
        },
    )
    await db.commit()

    logger.info("video_upload: job %s received video → video_ready", job_id)
    return {
        "job_id": job_id,
        "status": "video_ready",
        "video_url": video_url,
        "completed_at": now.isoformat(),
    }


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
    """Write the uploaded file to disk; return the saved Path."""
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
