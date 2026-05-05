"""Unit tests for VideoHandoffAgent."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.video.video_handoff  # noqa: F401

from agents.video.video_handoff import VideoHandoffAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_TITLE = "AI Marketing in 2025"
_SCRIPT = "In this video we explore how AI is transforming marketing teams worldwide."
_SCENES = [
    {
        "scene_number": 1,
        "duration_seconds": 30,
        "voiceover": "Welcome to the future of marketing.",
        "visual_direction": "Wide shot of a modern office.",
        "broll_url": "https://example.com/broll/office.mp4",
    }
]

_VALID_PARAMS = {
    "title": _TITLE,
    "script_text": _SCRIPT,
    "scenes": _SCENES,
}


def _make_db(brand_voice_row=None) -> AsyncMock:
    db = AsyncMock()
    mock_write = MagicMock()
    mock_write.rowcount = 1

    bv_result = MagicMock()
    if brand_voice_row:
        bv_result.fetchone.return_value = brand_voice_row
    else:
        bv_result.fetchone.return_value = None

    async def _execute_side_effect(query, params=None):
        sql = str(query)
        if "brand_voice" in sql and "SELECT" in sql:
            return bv_result
        return mock_write

    db.execute = AsyncMock(side_effect=_execute_side_effect)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params={**_VALID_PARAMS, **(params or {})},
        config={},
        db=db,
        llm=MagicMock(),
    )


def _patch_email(notified: bool = True):
    return patch(
        "agents.video.video_handoff.EmailIntegration.send_email",
        new_callable=AsyncMock,
        return_value=notified,
    )


# ── Validation ────────────────────────────────────────────────────────────────

class TestValidation:
    @pytest.mark.asyncio
    async def test_missing_title_returns_failed(self):
        db = _make_db()
        ctx = _ctx(db, params={"title": "", "script_text": _SCRIPT, "scenes": []})
        result = await VideoHandoffAgent().run(ctx)
        assert result.status == "failed"
        assert "title" in result.error.lower()

    @pytest.mark.asyncio
    async def test_missing_script_returns_failed(self):
        db = _make_db()
        ctx = _ctx(db, params={"title": _TITLE, "script_text": "", "scenes": []})
        result = await VideoHandoffAgent().run(ctx)
        assert result.status == "failed"
        assert "script_text" in result.error.lower()

    @pytest.mark.asyncio
    async def test_whitespace_title_returns_failed(self):
        db = _make_db()
        ctx = _ctx(db, params={"title": "   ", "script_text": _SCRIPT, "scenes": []})
        result = await VideoHandoffAgent().run(ctx)
        assert result.status == "failed"


# ── Happy path ────────────────────────────────────────────────────────────────

class TestHappyPath:
    @pytest.mark.asyncio
    async def test_success_status(self):
        db = _make_db()
        with _patch_email(True):
            result = await VideoHandoffAgent().run(_ctx(db))
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_returns_job_id_uuid(self):
        db = _make_db()
        with _patch_email():
            result = await VideoHandoffAgent().run(_ctx(db))
        import uuid
        uuid.UUID(result.data["job_id"])  # raises if not valid UUID

    @pytest.mark.asyncio
    async def test_upload_url_contains_base_url(self):
        db = _make_db()
        with _patch_email(), patch(
            "agents.video.video_handoff.settings"
        ) as mock_settings:
            mock_settings.base_url = "https://app.vikas.ai"
            mock_settings.smtp_host = "smtp.gmail.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "test@gmail.com"
            mock_settings.smtp_password = "pass"
            mock_settings.video_team_email = "team@company.com"
            result = await VideoHandoffAgent().run(_ctx(db))
        assert result.data["upload_url"].startswith("https://app.vikas.ai/video-upload/")

    @pytest.mark.asyncio
    async def test_upload_url_contains_token(self):
        db = _make_db()
        with _patch_email():
            result = await VideoHandoffAgent().run(_ctx(db))
        import uuid
        token_part = result.data["upload_url"].split("/")[-1]
        uuid.UUID(token_part)  # must be a valid UUID

    @pytest.mark.asyncio
    async def test_status_field_is_pending_video(self):
        db = _make_db()
        with _patch_email():
            result = await VideoHandoffAgent().run(_ctx(db))
        assert result.data["status"] == "pending_video"

    @pytest.mark.asyncio
    async def test_notified_true_when_email_succeeds(self):
        db = _make_db()
        with _patch_email(True):
            result = await VideoHandoffAgent().run(_ctx(db))
        assert result.data["notified"] is True

    @pytest.mark.asyncio
    async def test_notified_false_when_email_fails(self):
        db = _make_db()
        with _patch_email(False):
            result = await VideoHandoffAgent().run(_ctx(db))
        # still succeeds overall — email failure is non-fatal
        assert result.status == "success"
        assert result.data["notified"] is False


# ── DB writes ─────────────────────────────────────────────────────────────────

class TestDbWrites:
    def _video_job_insert_calls(self, db: AsyncMock) -> list:
        return [
            c for c in db.execute.call_args_list
            if "INSERT INTO video_jobs" in str(c[0][0])
        ]

    def _notified_at_update_calls(self, db: AsyncMock) -> list:
        return [
            c for c in db.execute.call_args_list
            if "notified_at" in str(c[0][0])
        ]

    @pytest.mark.asyncio
    async def test_video_job_inserted_once(self):
        db = _make_db()
        with _patch_email():
            await VideoHandoffAgent().run(_ctx(db))
        assert len(self._video_job_insert_calls(db)) == 1

    @pytest.mark.asyncio
    async def test_insert_contains_title(self):
        db = _make_db()
        with _patch_email():
            await VideoHandoffAgent().run(_ctx(db))
        calls = self._video_job_insert_calls(db)
        params = calls[0][0][1]
        assert params["title"] == _TITLE

    @pytest.mark.asyncio
    async def test_insert_contains_script(self):
        db = _make_db()
        with _patch_email():
            await VideoHandoffAgent().run(_ctx(db))
        calls = self._video_job_insert_calls(db)
        params = calls[0][0][1]
        assert params["script_text"] == _SCRIPT

    @pytest.mark.asyncio
    async def test_notified_at_updated_when_email_succeeds(self):
        db = _make_db()
        with _patch_email(True):
            await VideoHandoffAgent().run(_ctx(db))
        assert len(self._notified_at_update_calls(db)) == 1

    @pytest.mark.asyncio
    async def test_notified_at_not_updated_when_email_fails(self):
        db = _make_db()
        with _patch_email(False):
            await VideoHandoffAgent().run(_ctx(db))
        assert len(self._notified_at_update_calls(db)) == 0

    @pytest.mark.asyncio
    async def test_flush_called(self):
        db = _make_db()
        with _patch_email():
            await VideoHandoffAgent().run(_ctx(db))
        assert db.flush.call_count >= 1


# ── Brand voice loading ───────────────────────────────────────────────────────

class TestBrandVoice:
    @pytest.mark.asyncio
    async def test_brand_voice_from_params_skips_db_lookup(self):
        db = _make_db()
        params = {**_VALID_PARAMS, "brand_voice": {"tone": "professional"}}
        with _patch_email():
            result = await VideoHandoffAgent().run(_ctx(db, params=params))
        assert result.status == "success"
        bv_selects = [
            c for c in db.execute.call_args_list
            if "SELECT" in str(c[0][0]) and "brand_voice" in str(c[0][0])
        ]
        assert len(bv_selects) == 0

    @pytest.mark.asyncio
    async def test_brand_voice_loaded_from_db_when_not_in_params(self):
        bv_row = ("professional", ["AI", "automation"], ["spam"], {"length": "short"})
        db = _make_db(brand_voice_row=bv_row)
        with _patch_email():
            result = await VideoHandoffAgent().run(_ctx(db))
        assert result.status == "success"


# ── Email content ─────────────────────────────────────────────────────────────

class TestEmailContent:
    def _email_kwargs(self, mock_send) -> dict:
        """Return the kwargs passed to send_email (agent uses keyword args)."""
        return mock_send.call_args.kwargs

    @pytest.mark.asyncio
    async def test_email_subject_contains_title(self):
        db = _make_db()
        with patch(
            "agents.video.video_handoff.EmailIntegration.send_email",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = True
            await VideoHandoffAgent().run(_ctx(db))
        assert _TITLE in self._email_kwargs(mock_send)["subject"]

    @pytest.mark.asyncio
    async def test_email_body_contains_title(self):
        db = _make_db()
        with patch(
            "agents.video.video_handoff.EmailIntegration.send_email",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = True
            await VideoHandoffAgent().run(_ctx(db))
        assert _TITLE in self._email_kwargs(mock_send)["body_html"]

    @pytest.mark.asyncio
    async def test_email_body_contains_upload_url(self):
        db = _make_db()
        with patch(
            "agents.video.video_handoff.EmailIntegration.send_email",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = True
            result = await VideoHandoffAgent().run(_ctx(db))
        assert result.data["upload_url"] in self._email_kwargs(mock_send)["body_html"]

    @pytest.mark.asyncio
    async def test_email_body_contains_scene_count(self):
        db = _make_db()
        with patch(
            "agents.video.video_handoff.EmailIntegration.send_email",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = True
            await VideoHandoffAgent().run(_ctx(db))
        assert "1 scenes" in self._email_kwargs(mock_send)["body_html"]

    @pytest.mark.asyncio
    async def test_email_body_contains_estimated_seconds(self):
        db = _make_db()
        with patch(
            "agents.video.video_handoff.EmailIntegration.send_email",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = True
            await VideoHandoffAgent().run(_ctx(db))
        assert "30 seconds" in self._email_kwargs(mock_send)["body_html"]

    @pytest.mark.asyncio
    async def test_long_script_is_truncated_in_email_body(self):
        long_script = "x" * 500
        db = _make_db()
        params = {**_VALID_PARAMS, "script_text": long_script}
        with patch(
            "agents.video.video_handoff.EmailIntegration.send_email",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = True
            await VideoHandoffAgent().run(_ctx(db, params=params))
        assert "..." in self._email_kwargs(mock_send)["body_html"]

    @pytest.mark.asyncio
    async def test_deadline_included_in_email_when_provided(self):
        db = _make_db()
        params = {**_VALID_PARAMS, "deadline": "2025-06-01"}
        with patch(
            "agents.video.video_handoff.EmailIntegration.send_email",
            new_callable=AsyncMock,
        ) as mock_send:
            mock_send.return_value = True
            await VideoHandoffAgent().run(_ctx(db, params=params))
        assert "2025-06-01" in self._email_kwargs(mock_send)["body_html"]
