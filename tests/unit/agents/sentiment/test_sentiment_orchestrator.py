"""Unit tests for SentimentOrchestratorAgent — stage isolation and status logic."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.sentiment.sentiment_orchestrator  # noqa: F401

from agents.sentiment.sentiment_orchestrator import (
    SentimentOrchestratorAgent,
    _build_stage_params,
)
from core.agent_base import AgentContext, AgentResult

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(fetchall=MagicMock(return_value=[])))
    db.flush = AsyncMock()
    return db


def _make_ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID, run_id=RUN_ID,
        params=params or {},
        config={}, db=db, llm=MagicMock(),
    )


def _success(data: dict | None = None) -> AgentResult:
    return AgentResult(status="success", data=data or {"processed": 0})


def _failed(error: str = "stage error") -> AgentResult:
    return AgentResult(status="failed", error=error, data={})


# ── Stage param builder ───────────────────────────────────────────────────────

def test_build_stage_params_defaults() -> None:
    params = _build_stage_params({}, "my_scheme", "madurai", "2026-04-15")
    assert params["filter"]["scheme_key"] == "my_scheme"
    assert params["filter"]["batch_size"] == 200
    assert params["polarity"]["vader_threshold"] == pytest.approx(0.85)
    assert params["aggregator"]["signal_date"] == "2026-04-15"


def test_build_stage_params_overrides() -> None:
    raw = {"filter_batch": 50, "vader_threshold": 0.9}
    params = _build_stage_params(raw, "", "", "")
    assert params["filter"]["batch_size"] == 50
    assert params["polarity"]["vader_threshold"] == pytest.approx(0.9)


def test_all_six_stage_keys_present() -> None:
    params = _build_stage_params({}, "", "", "")
    assert set(params.keys()) == {"filter", "polarity", "theme", "entity", "aggregator", "spike"}


# ── Stage isolation: one failure → partial status ─────────────────────────────

@pytest.mark.asyncio
async def test_one_stage_failure_produces_partial_status() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    side_effects = [
        _success(),   # filter
        _failed(),    # polarity fails
        _success(),   # theme
        _success(),   # entity
        _success(),   # aggregator
        _success(),   # spike
    ]

    with patch("agents.sentiment.sentiment_orchestrator.REGISTRY") as MockReg:
        agent_mock = MagicMock()
        agent_mock.return_value.execute = AsyncMock(side_effect=side_effects)
        MockReg.__contains__ = MagicMock(return_value=True)
        MockReg.__getitem__ = MagicMock(return_value=agent_mock)

        result = await SentimentOrchestratorAgent().run(ctx)

    assert result.status == "partial"
    assert result.data["stages_succeeded"] == 5
    assert result.data["stages_failed"] == 1


# ── All stages succeed → success ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_stages_succeed_produces_success_status() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    with patch("agents.sentiment.sentiment_orchestrator.REGISTRY") as MockReg:
        agent_mock = MagicMock()
        agent_mock.return_value.execute = AsyncMock(return_value=_success())
        MockReg.__contains__ = MagicMock(return_value=True)
        MockReg.__getitem__ = MagicMock(return_value=agent_mock)

        result = await SentimentOrchestratorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["stages_succeeded"] == 6
    assert result.data["stages_failed"] == 0


# ── All stages fail → failed ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_stages_fail_produces_failed_status() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    with patch("agents.sentiment.sentiment_orchestrator.REGISTRY") as MockReg:
        agent_mock = MagicMock()
        agent_mock.return_value.execute = AsyncMock(return_value=_failed())
        MockReg.__contains__ = MagicMock(return_value=True)
        MockReg.__getitem__ = MagicMock(return_value=agent_mock)

        result = await SentimentOrchestratorAgent().run(ctx)

    assert result.status == "failed"
    assert result.data["stages_succeeded"] == 0


# ── Unregistered agent handled gracefully ─────────────────────────────────────

@pytest.mark.asyncio
async def test_unregistered_stage_agent_returns_partial() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    with patch("agents.sentiment.sentiment_orchestrator.REGISTRY") as MockReg:
        MockReg.__contains__ = MagicMock(return_value=False)
        MockReg.__getitem__ = MagicMock(side_effect=KeyError("not found"))

        result = await SentimentOrchestratorAgent().run(ctx)

    assert result.status == "failed"
    assert result.data["stages_failed"] == 6


# ── Stage exception isolation (unhandled raise in sub-agent) ──────────────────

@pytest.mark.asyncio
async def test_sub_agent_exception_isolated_to_one_stage() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    call_count = 0

    async def _execute_side_effect(sub_ctx: AgentContext) -> AgentResult:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("unexpected crash")
        return _success()

    with patch("agents.sentiment.sentiment_orchestrator.REGISTRY") as MockReg:
        agent_mock = MagicMock()
        agent_mock.return_value.execute = AsyncMock(side_effect=_execute_side_effect)
        MockReg.__contains__ = MagicMock(return_value=True)
        MockReg.__getitem__ = MagicMock(return_value=agent_mock)

        result = await SentimentOrchestratorAgent().run(ctx)

    assert result.status == "partial"
    assert result.data["stages_failed"] == 1
    assert result.data["stages_succeeded"] == 5


# ── Per-stage data present in result ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_result_contains_per_stage_data() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    with patch("agents.sentiment.sentiment_orchestrator.REGISTRY") as MockReg:
        agent_mock = MagicMock()
        agent_mock.return_value.execute = AsyncMock(return_value=_success({"processed": 42}))
        MockReg.__contains__ = MagicMock(return_value=True)
        MockReg.__getitem__ = MagicMock(return_value=agent_mock)

        result = await SentimentOrchestratorAgent().run(ctx)

    stages = result.data["stages"]
    assert "sentiment_filter" in stages
    assert "sentiment_polarity_classifier" in stages
    assert "sentiment_aggregator" in stages
    assert stages["sentiment_filter"]["data"]["processed"] == 42
