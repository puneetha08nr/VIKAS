"""video_handoff — creates a video job and notifies the video team via email.

No LLM. No avatar API. Pure handoff:
  1. Reads brand_voice from DB if not provided in params.
  2. Inserts a video_jobs row (status=pending_video, fresh upload_token).
  3. Builds the upload URL: {BASE_URL}/video-upload/{upload_token}
  4. Sends an HTML email notification to VIDEO_TEAM_EMAIL.
  5. Updates notified_at if email succeeded.
  6. Returns job_id + upload_url.

Input params:
  title          (str, required)
  script_text    (str, required)
  scenes         (list[dict], required) — scene_number, duration_seconds,
                   voiceover, visual_direction, broll_url
  broll_suggestions (list, optional)
  brand_voice    (dict, optional) — if omitted, read from brand_voice table
  deadline       (str, optional) — shown in email
"""
import json
import logging
import uuid

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import VideoHandoffOutput
from integrations.email import EmailIntegration

logger = logging.getLogger(__name__)


@register
class VideoHandoffAgent(BaseAgent):
    name = "video_handoff"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        title = str(ctx.params.get("title", "")).strip()
        script_text = str(ctx.params.get("script_text", "")).strip()

        if not title:
            return AgentResult(status="failed", error="title param is required")
        if not script_text:
            return AgentResult(status="failed", error="script_text param is required")

        scenes: list = ctx.params.get("scenes", [])
        broll_suggestions: list = ctx.params.get("broll_suggestions", [])
        brand_voice: dict = ctx.params.get("brand_voice") or {}
        deadline: str = ctx.params.get("deadline", "")

        # ── Step 1: Load brand_voice from DB if not passed ────────────────────
        if not brand_voice:
            brand_voice = await _load_brand_voice(ctx.org_id, ctx.db)

        # ── Step 2: Insert video_jobs row ─────────────────────────────────────
        job_id = str(uuid.uuid4())
        upload_token = str(uuid.uuid4())

        await ctx.db.execute(
            text(
                "INSERT INTO video_jobs "
                "  (id, org_id, title, script_text, scenes, broll_suggestions, "
                "   brand_voice, status, upload_token, created_at, updated_at) "
                "VALUES "
                "  (CAST(:job_id AS uuid), :org_id, :title, :script_text, "
                "   CAST(:scenes AS jsonb), CAST(:broll AS jsonb), "
                "   CAST(:brand_voice AS jsonb), 'pending_video', "
                "   CAST(:upload_token AS uuid), now(), now())"
            ),
            {
                "job_id": job_id,
                "org_id": ctx.org_id,
                "title": title,
                "script_text": script_text,
                "scenes": json.dumps(scenes),
                "broll": json.dumps(broll_suggestions),
                "brand_voice": json.dumps(brand_voice),
                "upload_token": upload_token,
            },
        )

        # ── Step 3: Build upload URL ──────────────────────────────────────────
        base_url = settings.base_url.rstrip("/")
        upload_url = f"{base_url}/video-upload/{upload_token}"

        # ── Step 4: Email notification ────────────────────────────────────────
        script_preview = script_text[:200] + ("..." if len(script_text) > 200 else "")
        total_seconds = sum(s.get("duration_seconds", 0) for s in scenes)
        deadline_row = f"<p><b>Deadline:</b> {deadline}</p>" if deadline else ""

        body_html = f"""
<h2>New video job is ready for production</h2>
<p><b>Title:</b> {title}</p>
<p><b>Script preview:</b> {script_preview}</p>
<p><b>Scenes:</b> {len(scenes)} scenes, est. {total_seconds} seconds</p>
{deadline_row}
<hr>
<p>Open the full brief and upload your finished video here:</p>
<a href="{upload_url}"
   style="display:inline-block;padding:10px 20px;background:#0F6E56;
          color:white;border-radius:6px;text-decoration:none">
  Open Video Brief &amp; Upload
</a>
<hr>
<p style="font-size:12px;color:#666">
  This link is unique to this job. Do not share it publicly.
</p>
""".strip()

        email = EmailIntegration(
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_user=settings.smtp_user,
            smtp_password=settings.smtp_password,
        )
        notified = await email.send_email(
            to=settings.video_team_email,
            subject=f"New video job ready: {title}",
            body_html=body_html,
        )

        # ── Step 5: Record notification timestamp ─────────────────────────────
        if notified:
            await ctx.db.execute(
                text(
                    "UPDATE video_jobs SET notified_at = now() "
                    "WHERE id = CAST(:job_id AS uuid)"
                ),
                {"job_id": job_id},
            )

        await ctx.db.flush()

        try:
            output = VideoHandoffOutput(
                job_id=job_id,
                upload_url=upload_url,
                status="pending_video",
                notified=notified,
            )
        except ValidationError as exc:
            logger.error("video_handoff: contract validation failed: %s", exc)
            return AgentResult(status="failed", error=str(exc))

        return AgentResult(
            status="success",
            data=output.model_dump(),
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _load_brand_voice(org_id: str, db: AsyncSession) -> dict:
    result = await db.execute(
        text(
            "SELECT tone, vocabulary, banned_phrases, style_rules "
            "FROM brand_voice WHERE org_id = :org_id LIMIT 1"
        ),
        {"org_id": org_id},
    )
    row = result.fetchone()
    if not row:
        return {}
    return {
        "tone": row[0] or "",
        "vocabulary": row[1] or [],
        "banned_phrases": row[2] or [],
        "style_rules": row[3] or {},
    }
