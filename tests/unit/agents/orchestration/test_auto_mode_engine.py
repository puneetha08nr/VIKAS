"""Unit tests for auto_mode_engine agent."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agent_base import AgentContext, AgentResult

ORG_ID = "00000000-0000-0000-0000-000000000001"
OPP_ID_1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
OPP_ID_2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _ctx(db, params=None):
    llm = MagicMock()
    return AgentContext(
        org_id=ORG_ID,
        run_id="run-1",
        params={} if params is None else params,
        config={},
        db=db,
        llm=llm,
    )


def _mock_db(opp_rows=None):
    if opp_rows is None:
        opp_rows = [(OPP_ID_1, 0.9), (OPP_ID_2, 0.7)]

    db = MagicMock()
    opp_result = MagicMock()
    mock_rows = []
    for opp_id, score in opp_rows:
        row = MagicMock()
        row.__getitem__ = lambda self, i, oid=opp_id, s=score: [oid, s][i]
        mock_rows.append(row)
    opp_result.fetchall = MagicMock(return_value=mock_rows)

    async def side_effect(query, params=None):
        sql = str(query)
        if "opportunities" in sql:
            return opp_result
        return MagicMock()

    db.execute = AsyncMock(side_effect=side_effect)
    db.flush = AsyncMock()
    return db


def _pipeline_success():
    return AgentResult(status="success", data={"stages_completed": 1, "status": "success"})


def _pipeline_failed():
    return AgentResult(status="failed", error="pipeline failed")


@pytest.mark.asyncio
async def test_success_with_opportunities():
    from agents.orchestration.auto_mode_engine import AutoModeEngineAgent
    db = _mock_db()
    registry = {
        "pipeline_orchestrator": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_pipeline_success()))),
    }
    with patch("agents.orchestration.auto_mode_engine.REGISTRY", registry):
        result = await AutoModeEngineAgent().execute(_ctx(db))
    assert result.status == "success"
    assert result.data["opportunities_selected"] == 2
    assert result.data["pipelines_triggered"] == 2


@pytest.mark.asyncio
async def test_dry_run_skips_pipelines():
    from agents.orchestration.auto_mode_engine import AutoModeEngineAgent
    db = _mock_db()
    pipeline_mock = MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_pipeline_success())))
    registry = {"pipeline_orchestrator": pipeline_mock}
    with patch("agents.orchestration.auto_mode_engine.REGISTRY", registry):
        result = await AutoModeEngineAgent().execute(_ctx(db, {"dry_run": True}))
    assert result.data["pipelines_triggered"] == 0
    assert result.data["opportunities_selected"] == 2
    pipeline_mock.return_value.execute.assert_not_called()


@pytest.mark.asyncio
async def test_no_opportunities():
    from agents.orchestration.auto_mode_engine import AutoModeEngineAgent
    db = _mock_db(opp_rows=[])
    registry = {"pipeline_orchestrator": MagicMock()}
    with patch("agents.orchestration.auto_mode_engine.REGISTRY", registry):
        result = await AutoModeEngineAgent().execute(_ctx(db))
    assert result.data["opportunities_selected"] == 0
    assert result.data["pipelines_triggered"] == 0


@pytest.mark.asyncio
async def test_pipeline_failure_counted():
    from agents.orchestration.auto_mode_engine import AutoModeEngineAgent
    db = _mock_db(opp_rows=[(OPP_ID_1, 0.9)])
    registry = {
        "pipeline_orchestrator": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_pipeline_failed()))),
    }
    with patch("agents.orchestration.auto_mode_engine.REGISTRY", registry):
        result = await AutoModeEngineAgent().execute(_ctx(db))
    assert result.status == "success"
    assert result.data["pipelines_triggered"] == 0


@pytest.mark.asyncio
async def test_custom_max_pipelines():
    from agents.orchestration.auto_mode_engine import AutoModeEngineAgent
    db = _mock_db()
    registry = {
        "pipeline_orchestrator": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=_pipeline_success()))),
    }
    with patch("agents.orchestration.auto_mode_engine.REGISTRY", registry):
        result = await AutoModeEngineAgent().execute(_ctx(db, {"max_pipelines": 1}))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_db_error_returns_empty_opps():
    from agents.orchestration.auto_mode_engine import AutoModeEngineAgent
    db = MagicMock()
    db.execute = AsyncMock(side_effect=Exception("DB down"))
    db.flush = AsyncMock()
    registry = {"pipeline_orchestrator": MagicMock()}
    with patch("agents.orchestration.auto_mode_engine.REGISTRY", registry):
        result = await AutoModeEngineAgent().execute(_ctx(db))
    assert result.status == "success"
    assert result.data["opportunities_selected"] == 0


@pytest.mark.asyncio
async def test_missing_pipeline_orchestrator():
    from agents.orchestration.auto_mode_engine import AutoModeEngineAgent
    db = _mock_db(opp_rows=[(OPP_ID_1, 0.9)])
    with patch("agents.orchestration.auto_mode_engine.REGISTRY", {}):
        result = await AutoModeEngineAgent().execute(_ctx(db))
    assert result.status == "success"
    assert result.data["pipelines_triggered"] == 0


@pytest.mark.asyncio
async def test_status_in_output():
    from agents.orchestration.auto_mode_engine import AutoModeEngineAgent
    db = _mock_db(opp_rows=[])
    with patch("agents.orchestration.auto_mode_engine.REGISTRY", {}):
        result = await AutoModeEngineAgent().execute(_ctx(db))
    assert result.data["status"] == "success"
