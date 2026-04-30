import pytest
from unittest.mock import AsyncMock, MagicMock

from core.cost_tracker import CostTracker


@pytest.fixture
def tracker() -> CostTracker:
    return CostTracker()


@pytest.fixture
def db() -> AsyncMock:
    return AsyncMock()


# ── add ───────────────────────────────────────────────────────────────────────

async def test_add_executes_update(tracker: CostTracker, db: AsyncMock) -> None:
    await tracker.add(
        org_id="org-1",
        run_id="run-1",
        model="gpt-4o-mini",
        tokens_in=100,
        tokens_out=50,
        cost_usd=0.01,
        db=db,
    )
    db.execute.assert_called_once()
    db.flush.assert_called_once()


async def test_add_passes_correct_params(tracker: CostTracker, db: AsyncMock) -> None:
    await tracker.add("org-1", "run-1", "gpt-4o-mini", 100, 50, 0.01, db)

    _, params = db.execute.call_args.args
    assert params["tokens_in"] == 100
    assert params["tokens_out"] == 50
    assert params["cost_usd"] == pytest.approx(0.01)
    assert params["model"] == "gpt-4o-mini"
    assert params["run_id"] == "run-1"


# ── get_daily_total ───────────────────────────────────────────────────────────

async def test_get_daily_total_returns_db_value(tracker: CostTracker, db: AsyncMock) -> None:
    scalar_result = MagicMock()
    scalar_result.scalar.return_value = 12.50
    db.execute = AsyncMock(return_value=scalar_result)

    total = await tracker.get_daily_total("org-1", db)

    assert total == pytest.approx(12.50)


async def test_get_daily_total_returns_zero_when_no_runs(
    tracker: CostTracker, db: AsyncMock
) -> None:
    scalar_result = MagicMock()
    scalar_result.scalar.return_value = 0.0
    db.execute = AsyncMock(return_value=scalar_result)

    total = await tracker.get_daily_total("org-1", db)

    assert total == 0.0


# ── check_limit ───────────────────────────────────────────────────────────────

async def test_check_limit_within_budget(tracker: CostTracker, db: AsyncMock) -> None:
    scalar_result = MagicMock()
    scalar_result.scalar.return_value = 10.0
    db.execute = AsyncMock(return_value=scalar_result)

    assert await tracker.check_limit("org-1", 50.0, db) is True


async def test_check_limit_exactly_at_limit_is_blocked(
    tracker: CostTracker, db: AsyncMock
) -> None:
    scalar_result = MagicMock()
    scalar_result.scalar.return_value = 50.0
    db.execute = AsyncMock(return_value=scalar_result)

    assert await tracker.check_limit("org-1", 50.0, db) is False


async def test_check_limit_over_budget(tracker: CostTracker, db: AsyncMock) -> None:
    scalar_result = MagicMock()
    scalar_result.scalar.return_value = 99.99
    db.execute = AsyncMock(return_value=scalar_result)

    assert await tracker.check_limit("org-1", 50.0, db) is False


# ── accumulation (integration-style with mocked DB) ───────────────────────────

async def test_daily_total_reflects_multiple_adds(tracker: CostTracker) -> None:
    """Two add() calls should each hit the DB; get_daily_total returns their sum."""
    db = AsyncMock()

    await tracker.add("org-1", "run-1", "gpt-4o-mini", 100, 50, 0.01, db)
    await tracker.add("org-1", "run-2", "gpt-4o-mini", 200, 100, 0.02, db)

    assert db.execute.call_count == 2
    assert db.flush.call_count == 2

    # Now verify get_daily_total queries the DB (returns whatever the DB says)
    scalar_result = MagicMock()
    scalar_result.scalar.return_value = 0.03
    db.execute = AsyncMock(return_value=scalar_result)

    total = await tracker.get_daily_total("org-1", db)
    assert total == pytest.approx(0.03)
