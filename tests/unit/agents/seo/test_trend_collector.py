"""Unit tests for TrendCollectorAgent."""
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.seo.trend_collector  # noqa: F401 — triggers @register

from agents.seo.trend_collector import (
    TrendCollectorAgent,
    _compute_momentum,
    _fetch_trends_sync,
)
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_TRACE = json.loads(
    (
        pathlib.Path(__file__).parent.parent.parent.parent
        / "golden_traces"
        / "trend_collector_trace.json"
    ).read_text()
)


# ── DB mock factory ───────────────────────────────────────────────────────────

def _make_db(validated_keywords: list[str] | None = None) -> AsyncMock:
    kw_rows = [(kw,) for kw in (validated_keywords or [])]

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        result.fetchall.return_value = kw_rows if "FROM keywords" in sql else []
        result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    return db


def _make_ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params=params or {},
        config={},
        db=db,
        llm=MagicMock(),
    )


# ── _compute_momentum unit tests ──────────────────────────────────────────────

def test_flat_trend_returns_five() -> None:
    values = [50.0] * 13
    assert _compute_momentum(values) == 5.0


def test_rising_trend_returns_above_five() -> None:
    values = [20.0] * 10 + [60.0, 70.0, 80.0]
    assert _compute_momentum(values) > 5.0


def test_falling_trend_returns_below_five() -> None:
    values = [80.0] * 10 + [20.0, 10.0, 5.0]
    assert _compute_momentum(values) < 5.0


def test_empty_values_returns_five() -> None:
    assert _compute_momentum([]) == 5.0


def test_momentum_capped_at_ten() -> None:
    values = [1.0] + [100.0] * 10
    assert _compute_momentum(values) <= 10.0


def test_momentum_floored_at_zero() -> None:
    values = [100.0] * 10 + [0.0, 0.0, 0.0]
    assert _compute_momentum(values) >= 0.0


def test_dormant_keyword_any_interest_scores_above_zero() -> None:
    # baseline_avg < 1 — was dormant, suddenly has interest
    values = [0.0] * 10 + [50.0, 60.0, 70.0]
    assert _compute_momentum(values) > 0.0


# ── Agent happy path ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_writes_signals_for_keywords_in_params() -> None:
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["ai marketing", "seo tools"]})

    mock_signals = [
        {"query": "ai marketing", "momentum": 7.5},
        {"query": "seo tools", "momentum": 4.2},
    ]

    with patch("agents.seo.trend_collector._fetch_trends_sync", return_value=mock_signals):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["signals_written"] == 2
    assert result.data["keywords_checked"] == 2


@pytest.mark.asyncio
async def test_fetches_validated_keywords_from_db_when_none_in_params() -> None:
    db = _make_db(validated_keywords=["content marketing", "keyword research"])
    ctx = _make_ctx(db)

    mock_signals = [
        {"query": "content marketing", "momentum": 6.0},
        {"query": "keyword research", "momentum": 5.0},
    ]

    with patch("agents.seo.trend_collector._fetch_trends_sync", return_value=mock_signals):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["signals_written"] == 2
    assert result.data["keywords_checked"] == 2


@pytest.mark.asyncio
async def test_no_keywords_returns_success_with_zero() -> None:
    db = _make_db(validated_keywords=[])
    ctx = _make_ctx(db)

    result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["signals_written"] == 0
    assert result.data["keywords_checked"] == 0


@pytest.mark.asyncio
async def test_tokens_used_is_zero() -> None:
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["ai marketing"]})

    with patch(
        "agents.seo.trend_collector._fetch_trends_sync",
        return_value=[{"query": "ai marketing", "momentum": 5.0}],
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


# ── Resilience tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pytrends_failure_writes_neutral_momentum_fallback() -> None:
    """If pytrends raises, agent falls back to momentum=5.0 for all keywords in batch."""
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["ai marketing", "seo tools"]})

    with patch(
        "agents.seo.trend_collector._fetch_trends_sync",
        side_effect=Exception("Google Trends rate limit"),
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    # Fallback signals still written
    assert result.data["signals_written"] == 2


@pytest.mark.asyncio
async def test_batches_five_keywords_per_pytrends_call() -> None:
    keywords = [f"keyword_{i}" for i in range(11)]
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": keywords})

    call_batches: list[list[str]] = []

    def _capture_batch(batch, timeframe, geo):
        call_batches.append(list(batch))
        return [{"query": kw, "momentum": 5.0} for kw in batch]

    with patch("agents.seo.trend_collector._fetch_trends_sync", side_effect=_capture_batch):
        await TrendCollectorAgent().run(ctx)

    # 11 keywords → batches of 5 → [5, 5, 1]
    assert len(call_batches) == 3
    assert len(call_batches[0]) == 5
    assert len(call_batches[1]) == 5
    assert len(call_batches[2]) == 1


@pytest.mark.asyncio
async def test_momentum_clamped_to_ten_on_write() -> None:
    """Momentum values > 10 from a misbehaving mock are clamped by TrendSignalOutput contract."""
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["trending keyword"]})

    with patch(
        "agents.seo.trend_collector._fetch_trends_sync",
        return_value=[{"query": "trending keyword", "momentum": 999.0}],
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["signals_written"] == 1
    # Verify INSERT was called with clamped value (sql is first positional arg)
    insert_call = [
        c for c in db.execute.call_args_list
        if "INSERT INTO trend_signals" in str(c.args[0])
    ]
    assert len(insert_call) == 1
    assert insert_call[0].args[1]["momentum"] == 10.0


@pytest.mark.asyncio
async def test_golden_trace_matches_expected_shape() -> None:
    """Verify the agent produces the fields the golden trace expects."""
    db = _make_db()
    ctx = _make_ctx(db, params=_TRACE["input_params"])

    with patch(
        "agents.seo.trend_collector._fetch_trends_sync",
        return_value=_TRACE["mock_pytrends_return"],
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == _TRACE["expected_result"]["status"]
    for field in _TRACE["expected_result"]["data_fields_present"]:
        assert field in result.data
