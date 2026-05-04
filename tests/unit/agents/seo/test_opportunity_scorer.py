"""Unit tests for OpportunityScorerAgent."""
from unittest.mock import AsyncMock, MagicMock

import pytest

import agents.seo.opportunity_scorer  # noqa: F401 — triggers @register

from agents.seo.opportunity_scorer import OpportunityScorerAgent
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


def _make_db(keyword_rows: list) -> AsyncMock:
    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        # Keywords SELECT → fetchall returns the seeded rows
        result.fetchall.return_value = keyword_rows if "FROM keywords" in sql else []
        # trend_signals SELECT → fetchone returns None (no trend data → 5.0 fallback)
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


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_creates_opportunities_for_validated_keywords() -> None:
    rows = [
        _kw_row("id-1", "ai marketing", 3000, 40.0, 2.5, "commercial"),
        _kw_row("id-2", "seo tools", 1500, 30.0, 1.8, "informational"),
        _kw_row("id-3", "content ai", 800, 20.0, 1.2, "informational"),
    ]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    result = await OpportunityScorerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["opportunities_created"] == 3
    # _create_run_record(1) + SELECT keywords(1) + per-kw [trend_signals(1)+INSERT(1)]*3 + _audit(1) = 9
    assert db.execute.call_count == 9
    assert db.flush.called


@pytest.mark.asyncio
async def test_composite_score_greater_than_zero() -> None:
    rows = [_kw_row("id-1", "ai marketing", 3000, 40.0, 2.5, "commercial")]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    result = await OpportunityScorerAgent().run(ctx)

    assert result.data["score_range"]["max"] > 0


@pytest.mark.asyncio
async def test_skips_already_scored_keywords() -> None:
    # DB returns only 1 unscored keyword (the WHERE NOT EXISTS filters the rest)
    rows = [_kw_row("id-2", "seo tools", 1500, 30.0, 1.8, "informational")]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    result = await OpportunityScorerAgent().run(ctx)

    assert result.data["opportunities_created"] == 1


@pytest.mark.asyncio
async def test_commercial_scores_higher_than_navigational() -> None:
    commercial = _kw_row("id-c", "buy ai software", 2000, 30.0, 3.0, "commercial")
    navigational = _kw_row("id-n", "openai website", 2000, 30.0, 3.0, "navigational")

    def _db_for(kw_row):
        def _side(query, params=None):
            sql = str(query)
            result = MagicMock()
            result.fetchall.return_value = [kw_row] if "FROM keywords" in sql else []
            result.fetchone.return_value = None  # no trend data → 5.0 fallback
            return result

        db = AsyncMock()
        db.execute = AsyncMock(side_effect=_side)
        db.flush = AsyncMock()
        return db

    result_c = await OpportunityScorerAgent().run(_make_ctx(_db_for(commercial)))
    result_n = await OpportunityScorerAgent().run(_make_ctx(_db_for(navigational)))

    assert result_c.data["score_range"]["max"] > result_n.data["score_range"]["max"]


@pytest.mark.asyncio
async def test_no_validated_keywords_returns_success() -> None:
    db = _make_db([])
    ctx = _make_ctx(db)

    result = await OpportunityScorerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["opportunities_created"] == 0
    assert "No unscored" in result.data["message"]


@pytest.mark.asyncio
async def test_tokens_used_is_zero() -> None:
    rows = [_kw_row("id-1", "ai marketing", 3000, 40.0, 2.5, "informational")]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    result = await OpportunityScorerAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


@pytest.mark.asyncio
async def test_top_opportunity_is_highest_composite() -> None:
    rows = [
        _kw_row("id-1", "high volume kw", 8000, 10.0, 5.0, "commercial"),
        _kw_row("id-2", "low volume kw", 100, 80.0, 0.1, "navigational"),
    ]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    result = await OpportunityScorerAgent().run(ctx)

    assert result.data["top_opportunity"] == "high volume kw"
    assert result.data["score_range"]["max"] >= result.data["score_range"]["min"]


@pytest.mark.asyncio
async def test_keyword_ids_param_is_passed_through() -> None:
    """keyword_ids in params must appear in the SQL query params."""
    rows = [_kw_row("id-1", "filtered kw", 1000, 20.0, 1.0, "informational")]
    db = _make_db(rows)
    ctx = _make_ctx(db, params={"keyword_ids": ["id-1", "id-2"]})

    result = await OpportunityScorerAgent().run(ctx)

    # call_args_list[0] = _create_run_record INSERT, [1] = the SELECT with keyword_ids
    select_call_params = db.execute.call_args_list[1][0][1]
    assert "keyword_ids" in select_call_params
    assert result.data["opportunities_created"] == 1
