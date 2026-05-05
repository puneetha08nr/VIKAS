"""Unit tests for pipeline_orchestrator agent."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agent_base import AgentContext, AgentResult

ORG_ID = "00000000-0000-0000-0000-000000000001"
OPP_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
ARTICLE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _ctx(db, params=None):
    llm = MagicMock()
    return AgentContext(
        org_id=ORG_ID,
        run_id="run-1",
        params={"opportunity_id": OPP_ID} if params is None else params,
        config={},
        db=db,
        llm=llm,
    )


def _mock_db():
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    return db


def _cd_success():
    return AgentResult(status="success", data={"article_id": ARTICLE_ID, "status": "success"})


def _cd_failed():
    return AgentResult(status="failed", error="content_director broke")


def _wp_success():
    return AgentResult(status="success", data={"published_url": "https://example.com/post"})


@pytest.mark.asyncio
async def test_missing_opportunity_id_fails():
    from agents.orchestration.pipeline_orchestrator import PipelineOrchestratorAgent
    db = _mock_db()
    result = await PipelineOrchestratorAgent().execute(_ctx(db, {}))
    assert result.status == "failed"
    assert "opportunity_id" in result.error


@pytest.mark.asyncio
async def test_success_content_director_only():
    from agents.orchestration.pipeline_orchestrator import PipelineOrchestratorAgent
    db = _mock_db()
    registry = {
        "content_director": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_cd_success()))),
    }
    with patch("agents.orchestration.pipeline_orchestrator.REGISTRY", registry):
        result = await PipelineOrchestratorAgent().execute(_ctx(db))
    assert result.status == "success"
    assert result.data["stages_completed"] == 1
    assert result.data["stages_failed"] == 0


@pytest.mark.asyncio
async def test_content_director_failure_gives_partial():
    from agents.orchestration.pipeline_orchestrator import PipelineOrchestratorAgent
    db = _mock_db()
    registry = {
        "content_director": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_cd_failed()))),
    }
    with patch("agents.orchestration.pipeline_orchestrator.REGISTRY", registry):
        result = await PipelineOrchestratorAgent().execute(_ctx(db))
    assert result.data["status"] == "failed"
    assert result.data["stages_failed"] == 1


@pytest.mark.asyncio
async def test_auto_publish_triggers_wp():
    from agents.orchestration.pipeline_orchestrator import PipelineOrchestratorAgent
    db = _mock_db()
    registry = {
        "content_director": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_cd_success()))),
        "wordpress_publisher": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_wp_success()))),
    }
    with patch("agents.orchestration.pipeline_orchestrator.REGISTRY", registry):
        result = await PipelineOrchestratorAgent().execute(_ctx(db, {"opportunity_id": OPP_ID, "auto_publish": True}))
    assert result.data["stages_completed"] == 2
    registry["wordpress_publisher"].return_value.execute.assert_called_once()


@pytest.mark.asyncio
async def test_no_auto_publish_skips_wp():
    from agents.orchestration.pipeline_orchestrator import PipelineOrchestratorAgent
    db = _mock_db()
    wp_mock = MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_wp_success())))
    registry = {
        "content_director": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_cd_success()))),
        "wordpress_publisher": wp_mock,
    }
    with patch("agents.orchestration.pipeline_orchestrator.REGISTRY", registry):
        result = await PipelineOrchestratorAgent().execute(_ctx(db))  # auto_publish=False by default
    wp_mock.return_value.execute.assert_not_called()
    assert result.data["stages_completed"] == 1


@pytest.mark.asyncio
async def test_db_pipeline_run_inserted():
    from agents.orchestration.pipeline_orchestrator import PipelineOrchestratorAgent
    db = _mock_db()
    registry = {
        "content_director": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_cd_success()))),
    }
    with patch("agents.orchestration.pipeline_orchestrator.REGISTRY", registry):
        await PipelineOrchestratorAgent().execute(_ctx(db))
    calls = [str(c.args[0]) for c in db.execute.call_args_list if "pipeline_runs" in str(c.args[0])]
    assert len(calls) >= 1


@pytest.mark.asyncio
async def test_db_flush_called():
    from agents.orchestration.pipeline_orchestrator import PipelineOrchestratorAgent
    db = _mock_db()
    registry = {
        "content_director": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_cd_success()))),
    }
    with patch("agents.orchestration.pipeline_orchestrator.REGISTRY", registry):
        await PipelineOrchestratorAgent().execute(_ctx(db))
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_opportunity_id_in_output():
    from agents.orchestration.pipeline_orchestrator import PipelineOrchestratorAgent
    db = _mock_db()
    registry = {
        "content_director": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_cd_success()))),
    }
    with patch("agents.orchestration.pipeline_orchestrator.REGISTRY", registry):
        result = await PipelineOrchestratorAgent().execute(_ctx(db))
    assert result.data["opportunity_id"] == OPP_ID
