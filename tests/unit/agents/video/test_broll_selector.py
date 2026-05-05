"""Unit tests for BrollSelectorAgent."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.video.broll_selector  # noqa: F401

from agents.video.broll_selector import BrollSelectorAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_FAKE_VIDEOS = [
    {"pexels_id": 111, "video_url": "https://v.pexels.com/1.mp4",
     "preview_url": "https://v.pexels.com/1p.mp4", "width": 1920, "height": 1080},
    {"pexels_id": 222, "video_url": "https://v.pexels.com/2.mp4",
     "preview_url": "https://v.pexels.com/2p.mp4", "width": 1280, "height": 720},
]


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    return db


def _ctx(db, params=None):
    return AgentContext(
        org_id=ORG_ID, run_id=RUN_ID,
        params=params or {}, config={}, db=db, llm=MagicMock(),
    )


def _patch_pexels(videos=None):
    v = videos if videos is not None else _FAKE_VIDEOS
    m = MagicMock()
    m.search_videos = AsyncMock(return_value=v)
    return patch("agents.video.broll_selector.PexelsIntegration", return_value=m)


class TestValidation:
    @pytest.mark.asyncio
    async def test_missing_scenes_returns_failed(self):
        db = _make_db()
        result = await BrollSelectorAgent().run(_ctx(db, {}))
        assert result.status == "failed"
        assert "scene_descriptions" in result.error

    @pytest.mark.asyncio
    async def test_empty_scenes_list_returns_failed(self):
        db = _make_db()
        result = await BrollSelectorAgent().run(_ctx(db, {"scene_descriptions": []}))
        assert result.status == "failed"


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_success_status(self):
        db = _make_db()
        params = {"scene_descriptions": ["office workers at laptops"]}
        with _patch_pexels():
            result = await BrollSelectorAgent().run(_ctx(db, params))
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_scenes_processed_count(self):
        db = _make_db()
        params = {"scene_descriptions": ["scene A", "scene B"]}
        with _patch_pexels():
            result = await BrollSelectorAgent().run(_ctx(db, params))
        assert result.data["scenes_processed"] == 2

    @pytest.mark.asyncio
    async def test_db_insert_called_per_video(self):
        db = _make_db()
        params = {"scene_descriptions": ["office"]}
        with _patch_pexels(_FAKE_VIDEOS):
            await BrollSelectorAgent().run(_ctx(db, params))
        inserts = [c for c in db.execute.call_args_list
                   if "INSERT INTO broll_suggestions" in str(c[0][0])]
        assert len(inserts) == len(_FAKE_VIDEOS)

    @pytest.mark.asyncio
    async def test_placeholder_inserted_when_pexels_empty(self):
        db = _make_db()
        params = {"scene_descriptions": ["very obscure scene"]}
        with _patch_pexels([]):
            result = await BrollSelectorAgent().run(_ctx(db, params))
        inserts = [c for c in db.execute.call_args_list
                   if "INSERT INTO broll_suggestions" in str(c[0][0])]
        assert len(inserts) == 1  # placeholder
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_flush_called(self):
        db = _make_db()
        params = {"scene_descriptions": ["scene"]}
        with _patch_pexels():
            await BrollSelectorAgent().run(_ctx(db, params))
        assert db.flush.call_count >= 1

    @pytest.mark.asyncio
    async def test_total_suggestions_found_correct(self):
        db = _make_db()
        params = {"scene_descriptions": ["scene A", "scene B"]}
        with _patch_pexels(_FAKE_VIDEOS):
            result = await BrollSelectorAgent().run(_ctx(db, params))
        assert result.data["total_suggestions_found"] == len(_FAKE_VIDEOS) * 2
