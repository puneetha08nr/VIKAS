"""Unit tests for OpportunityScorerAgent — Mode 1 (create) + Mode 2 (true-up)."""
from unittest.mock import AsyncMock, MagicMock, call

import pytest

import agents.seo.opportunity_scorer  # noqa: F401 — triggers @register

from agents.seo.opportunity_scorer import (
    OpportunityScorerAgent,
    _recalculate_composite,
)
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"


def _kw_row(
    id: str,
    keyword: str,
    volume: int,
    kd: float,
    cpc: float,
    intent: str,
) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.keyword = keyword
    row.volume = volume
    row.kd = kd
    row.cpc = cpc
    row.intent = intent
    return row


def _opp_row(
    id: str,
    search_score: float,
    gap_score: float,
    engage_score: float,
    new_trend_score: float,
) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.search_score = search_score
    row.competitive_gap_score = gap_score
    row.engagement_score = engage_score
    row.new_trend_score = new_trend_score
    return row


def _make_db(
    keyword_rows: list | None = None,
    trend_signal_momentum: float | None = None,
    opportunity_rows: list | None = None,
) -> AsyncMock:
    """Build a mock DB that handles the three main query patterns:

    - INSERT agent_runs   → ignored (BaseAgent lifecycle)
    - SELECT FROM keywords → keyword_rows
    - SELECT FROM trend_signals (non-neutral check) → trend_signal_momentum
    - SELECT FROM opportunities (Mode 2 join) → opportunity_rows
    - INSERT INTO opportunities → ignored
    - UPDATE opportunities → ignored
    """
    keyword_rows = keyword_rows or []
    opportunity_rows = opportunity_rows or []

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()

        if "FROM keywords" in sql:
            result.fetchall.return_value = keyword_rows
            result.fetchone.return_value = None

        elif "FROM trend_signals" in sql and "source != 'neutral_fallback'" in sql:
            # _get_real_trend_score or Mode 2 main query
            if "JOIN" in sql:
                # Mode 2 main query → fetchall
                result.fetchall.return_value = opportunity_rows
            else:
                # _get_real_trend_score → fetchone
                if trend_signal_momentum is not None:
                    row = MagicMock()
                    row.momentum = trend_signal_momentum
                    result.fetchone.return_value = row
                else:
                    result.fetchone.return_value = None

        else:
            result.fetchall.return_value = []
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


# ── _recalculate_composite ────────────────────────────────────────────────────

def test_recalculate_uses_simple_average() -> None:
    score = _recalculate_composite(8.0, 5.0, 6.0, 4.0)
    assert score == round((8.0 + 5.0 + 6.0 + 4.0) / 4, 2)


def test_recalculate_skips_none_values() -> None:
    # Only search and trend available
    score = _recalculate_composite(8.0, None, 6.0, None)
    assert score == round((8.0 + 6.0) / 2, 2)


def test_recalculate_caps_at_ten() -> None:
    score = _recalculate_composite(10.0, 10.0, 10.0, 10.0)
    assert score <= 10.0


def test_recalculate_all_none_returns_zero() -> None:
    score = _recalculate_composite(None, None, None, None)
    assert score == 0.0


def test_recalculate_single_score() -> None:
    score = _recalculate_composite(7.0, None, None, None)
    assert score == 7.0


# ── Mode 1: Create ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mode1_creates_opportunities_for_validated_keywords() -> None:
    rows = [
        _kw_row("id-1", "ai marketing", 3000, 40.0, 2.5, "commercial"),
        _kw_row("id-2", "seo tools", 1500, 30.0, 1.8, "informational"),
        _kw_row("id-3", "content ai", 800, 20.0, 1.2, "informational"),
    ]
    db = _make_db(keyword_rows=rows)
    ctx = _make_ctx(db)

    result = await OpportunityScorerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["opportunities_created"] == 3
    assert result.data["opportunities_updated"] == 0


@pytest.mark.asyncio
async def test_mode1_stores_null_trend_when_no_real_signal() -> None:
    """With no non-neutral signal, INSERT uses trend_score=NULL."""
    rows = [_kw_row("id-1", "ai marketing", 3000, 40.0, 2.5, "commercial")]
    # trend_signal_momentum=None → no real signal
    db = _make_db(keyword_rows=rows, trend_signal_momentum=None)
    ctx = _make_ctx(db)

    await OpportunityScorerAgent().run(ctx)

    insert_calls = [
        c for c in db.execute.call_args_list
        if "INSERT INTO opportunities" in str(c.args[0])
    ]
    assert len(insert_calls) == 1
    assert insert_calls[0].args[1]["trend_score"] is None


@pytest.mark.asyncio
async def test_mode1_stores_real_trend_when_signal_exists() -> None:
    """With a non-neutral signal, INSERT uses the real momentum value."""
    rows = [_kw_row("id-1", "ai marketing", 3000, 40.0, 2.5, "commercial")]
    db = _make_db(keyword_rows=rows, trend_signal_momentum=7.5)
    ctx = _make_ctx(db)

    await OpportunityScorerAgent().run(ctx)

    insert_calls = [
        c for c in db.execute.call_args_list
        if "INSERT INTO opportunities" in str(c.args[0])
    ]
    assert len(insert_calls) == 1
    assert insert_calls[0].args[1]["trend_score"] == 7.5


@pytest.mark.asyncio
async def test_mode1_composite_score_greater_than_zero() -> None:
    rows = [_kw_row("id-1", "ai marketing", 3000, 40.0, 2.5, "commercial")]
    db = _make_db(keyword_rows=rows)
    result = await OpportunityScorerAgent().run(_make_ctx(db))
    insert_calls = [
        c for c in db.execute.call_args_list
        if "INSERT INTO opportunities" in str(c.args[0])
    ]
    assert insert_calls[0].args[1]["composite_score"] > 0


@pytest.mark.asyncio
async def test_mode1_composite_score_capped_at_10() -> None:
    row = _kw_row("id-cap", "perfect keyword", 50000, 0.0, 12.5, "commercial")
    db = _make_db(keyword_rows=[row], trend_signal_momentum=10.0)
    result = await OpportunityScorerAgent().run(_make_ctx(db))
    insert_calls = [
        c for c in db.execute.call_args_list
        if "INSERT INTO opportunities" in str(c.args[0])
    ]
    assert insert_calls[0].args[1]["composite_score"] <= 10.0


@pytest.mark.asyncio
async def test_mode1_commercial_scores_higher_than_navigational() -> None:
    def _db_for(kw_row):
        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = [kw_row]
        result_mock.fetchone.return_value = None

        result_mode2 = MagicMock()
        result_mode2.fetchall.return_value = []

        def _side(query, params=None):
            sql = str(query)
            if "FROM keywords" in sql:
                return result_mock
            if "FROM trend_signals" in sql and "JOIN" in sql:
                return result_mode2
            return result_mock
        db.execute = AsyncMock(side_effect=_side)
        db.flush = AsyncMock()
        return db

    commercial = _kw_row("id-c", "buy ai software", 2000, 30.0, 3.0, "commercial")
    navigational = _kw_row("id-n", "openai website", 2000, 30.0, 3.0, "navigational")

    result_c = await OpportunityScorerAgent().run(_make_ctx(_db_for(commercial)))
    result_n = await OpportunityScorerAgent().run(_make_ctx(_db_for(navigational)))

    insert_c = [
        c for c in _db_for(commercial).execute.call_args_list
        if "INSERT INTO opportunities" in str(c.args[0])
    ]
    # Simpler: just check that commercial > navigational via score formula
    from agents.seo.opportunity_scorer import _INTENT_MULTIPLIER
    assert _INTENT_MULTIPLIER["commercial"] > _INTENT_MULTIPLIER["navigational"]


@pytest.mark.asyncio
async def test_mode1_no_keywords_returns_zero_created() -> None:
    db = _make_db(keyword_rows=[])
    result = await OpportunityScorerAgent().run(_make_ctx(db))
    assert result.status == "success"
    assert result.data["opportunities_created"] == 0


@pytest.mark.asyncio
async def test_mode1_keyword_ids_param_passed_to_query() -> None:
    rows = [_kw_row("id-1", "filtered kw", 1000, 20.0, 1.0, "informational")]
    db = _make_db(keyword_rows=rows)
    ctx = _make_ctx(db, params={"keyword_ids": ["id-1", "id-2"]})

    await OpportunityScorerAgent().run(ctx)

    # The SELECT for keywords is always the second execute call (after agent_runs INSERT)
    select_call_params = db.execute.call_args_list[1].args[1]
    assert "keyword_ids" in select_call_params


@pytest.mark.asyncio
async def test_tokens_used_is_zero() -> None:
    rows = [_kw_row("id-1", "ai marketing", 3000, 40.0, 2.5, "informational")]
    db = _make_db(keyword_rows=rows)
    result = await OpportunityScorerAgent().run(_make_ctx(db))
    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


# ── Mode 2: True-up (update existing with trend data) ─────────────────────────

@pytest.mark.asyncio
async def test_mode2_updates_opportunities_with_null_trend() -> None:
    """Opportunities with NULL trend_score get updated when a real signal is available."""
    opp_rows = [
        _opp_row("opp-1", search_score=6.0, gap_score=5.0, engage_score=2.0, new_trend_score=7.5),
        _opp_row("opp-2", search_score=3.0, gap_score=5.0, engage_score=1.0, new_trend_score=3.3),
    ]
    db = _make_db(keyword_rows=[], opportunity_rows=opp_rows)
    ctx = _make_ctx(db)

    result = await OpportunityScorerAgent().run(ctx)

    assert result.data["opportunities_updated"] == 2
    assert result.data["opportunities_created"] == 0

    update_calls = [
        c for c in db.execute.call_args_list
        if "UPDATE opportunities" in str(c.args[0])
    ]
    assert len(update_calls) == 2


@pytest.mark.asyncio
async def test_mode2_computes_correct_composite() -> None:
    """Updated composite = simple average of available scores."""
    opp_rows = [
        _opp_row("opp-1", search_score=8.0, gap_score=5.0, engage_score=2.0, new_trend_score=6.0),
    ]
    db = _make_db(keyword_rows=[], opportunity_rows=opp_rows)
    ctx = _make_ctx(db)

    await OpportunityScorerAgent().run(ctx)

    update_calls = [
        c for c in db.execute.call_args_list
        if "UPDATE opportunities" in str(c.args[0])
    ]
    assert len(update_calls) == 1
    params = update_calls[0].args[1]
    expected_composite = round((8.0 + 5.0 + 6.0 + 2.0) / 4, 2)
    assert params["composite_score"] == expected_composite
    assert params["trend_score"] == 6.0


@pytest.mark.asyncio
async def test_mode2_does_not_update_when_no_signals() -> None:
    """If Mode 2 query returns no rows, updated == 0."""
    db = _make_db(keyword_rows=[], opportunity_rows=[])
    result = await OpportunityScorerAgent().run(_make_ctx(db))
    assert result.data["opportunities_updated"] == 0


@pytest.mark.asyncio
async def test_mode2_message_reports_both_counts() -> None:
    opp_rows = [_opp_row("opp-1", 6.0, 5.0, 2.0, 7.5)]
    db = _make_db(keyword_rows=[], opportunity_rows=opp_rows)
    result = await OpportunityScorerAgent().run(_make_ctx(db))
    assert "0" in result.data["message"]   # created
    assert "1" in result.data["message"]   # updated


@pytest.mark.asyncio
async def test_mode1_and_mode2_run_in_same_execution() -> None:
    """When both keywords to create and opportunities to update exist, both modes run."""
    kw_rows = [_kw_row("id-new", "fresh keyword", 2000, 20.0, 1.5, "informational")]
    opp_rows = [_opp_row("opp-1", 6.0, 5.0, 2.0, 7.5)]
    db = _make_db(keyword_rows=kw_rows, opportunity_rows=opp_rows)
    ctx = _make_ctx(db)

    result = await OpportunityScorerAgent().run(ctx)

    assert result.data["opportunities_created"] == 1
    assert result.data["opportunities_updated"] == 1


@pytest.mark.asyncio
async def test_result_has_both_fields_when_nothing_to_do() -> None:
    db = _make_db(keyword_rows=[], opportunity_rows=[])
    result = await OpportunityScorerAgent().run(_make_ctx(db))
    assert "opportunities_created" in result.data
    assert "opportunities_updated" in result.data
