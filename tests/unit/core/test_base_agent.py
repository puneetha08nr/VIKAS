import pytest
from unittest.mock import AsyncMock, MagicMock

from core.agent_base import AgentContext, AgentResult, BaseAgent, PreflightResult
from core.agent_registry import REGISTRY, register


# ── fixture agent ─────────────────────────────────────────────────────────────

@register
class FakeAgent(BaseAgent):
    name = "fake_agent"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        return AgentResult(status="success", data={"result": "ok"}, tokens_used=10, cost_usd=0.001)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="mock llm response")
    return llm


@pytest.fixture
def ctx(mock_db: AsyncMock, mock_llm: MagicMock) -> AgentContext:
    return AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        params={},
        config={},
        db=mock_db,
        llm=mock_llm,
    )


# ── tests ─────────────────────────────────────────────────────────────────────

async def test_successful_run_returns_success(ctx: AgentContext, mock_db: AsyncMock) -> None:
    result = await FakeAgent().run(ctx)

    assert result.status == "success"
    assert result.data == {"result": "ok"}


async def test_successful_run_creates_and_finalises_agent_run_record(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    await FakeAgent().run(ctx)

    # _create_run_record (INSERT) + _audit (UPDATE) = 2 execute calls
    assert mock_db.execute.call_count == 2
    assert mock_db.commit.called


async def test_successful_run_records_cost(ctx: AgentContext, mock_db: AsyncMock) -> None:
    await FakeAgent().run(ctx)

    # The UPDATE call in _audit includes cost_usd
    update_call_args = mock_db.execute.call_args_list[1]
    params = update_call_args[0][1]  # positional arg: params dict
    assert params["cost_usd"] == pytest.approx(0.001)


async def test_preflight_failure_skips_execute_and_returns_failed(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    class FailingPreflightAgent(BaseAgent):
        name = "failing_preflight"
        tier = "fast"

        def preflight(self, ctx: AgentContext) -> PreflightResult:
            return PreflightResult(ok=False, reason="missing required param: seed")

        async def execute(self, ctx: AgentContext) -> AgentResult:
            raise AssertionError("execute should not be called")

    result = await FailingPreflightAgent().run(ctx)

    assert result.status == "failed"
    assert "missing required param: seed" in (result.error or "")


async def test_execute_exception_returns_failed(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    class BrokenAgent(BaseAgent):
        name = "broken_agent"
        tier = "fast"

        async def execute(self, ctx: AgentContext) -> AgentResult:
            raise ValueError("downstream API unreachable")

    result = await BrokenAgent().run(ctx)

    assert result.status == "failed"
    assert "downstream API unreachable" in (result.error or "")


async def test_duration_ms_is_populated(ctx: AgentContext) -> None:
    result = await FakeAgent().run(ctx)
    assert result.duration_ms >= 0


async def test_agent_registered_in_registry() -> None:
    assert "fake_agent" in REGISTRY
    agent = REGISTRY["fake_agent"]()
    assert isinstance(agent, FakeAgent)
