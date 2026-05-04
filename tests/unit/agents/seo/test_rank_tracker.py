"""Unit tests for RankTrackerAgent."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.seo.rank_tracker  # noqa: F401 — triggers @register

from agents.seo.rank_tracker import RankTrackerAgent, _classify
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"
SITE_URL = "https://example.com"

_GSC_ROWS = [
    {"query": "ai marketing automation", "clicks": 142, "impressions": 1500, "ctr": 0.094, "position": 4.2},
    {"query": "seo quick win keyword",   "clicks": 5,   "impressions": 400,  "ctr": 0.012, "position": 18.3},
    {"query": "barely ranking term",     "clicks": 1,   "impressions": 200,  "ctr": 0.005, "position": 45.0},
]


def _kw_row(id: str, keyword: str) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.keyword = keyword
    return row


def _make_db(kw_rows: list, prev_positions: list | None = None) -> AsyncMock:
    """prev_positions: list of (keyword_id, position) tuples for rank_tracking SELECT."""
    prev_positions = prev_positions or []

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM keywords" in sql:
            result.fetchall.return_value = kw_rows
        elif "FROM rank_tracking" in sql:
            result.fetchall.return_value = prev_positions
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
        params={"site_url": SITE_URL, **(params or {})},
        config={},
        db=db,
        llm=MagicMock(),
    )


# ── Unit: classification ──────────────────────────────────────────────────────

def test_position_1_to_10_is_ranking() -> None:
    assert _classify(1.0) == "ranking"
    assert _classify(9.9) == "ranking"
    assert _classify(10.0) == "ranking"


def test_position_11_to_30_is_quick_win() -> None:
    assert _classify(11.0) == "quick_win"
    assert _classify(18.3) == "quick_win"
    assert _classify(30.0) == "quick_win"


def test_position_above_30_is_not_ranking() -> None:
    assert _classify(30.1) == "not_ranking"
    assert _classify(45.0) == "not_ranking"
    assert _classify(100.0) == "not_ranking"


def test_none_position_is_not_ranking() -> None:
    assert _classify(None) == "not_ranking"


# ── Agent: happy path ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tracks_all_keywords_and_counts_correctly() -> None:
    rows = [
        _kw_row("kw-1", "ai marketing automation"),   # position 4.2  → ranking
        _kw_row("kw-2", "seo quick win keyword"),      # position 18.3 → quick_win
        _kw_row("kw-3", "completely unknown keyword"),  # not in GSC  → not_ranking
    ]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    with patch("agents.seo.rank_tracker.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await RankTrackerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total_tracked"] == 3
    assert result.data["ranking"] == 1
    assert result.data["quick_wins"] == 1
    assert result.data["not_ranking"] == 1
    assert db.flush.called


@pytest.mark.asyncio
async def test_quick_win_boundary_position_30() -> None:
    rows = [_kw_row("kw-1", "boundary keyword")]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    boundary_gsc = [{"query": "boundary keyword", "clicks": 1,
                     "impressions": 100, "ctr": 0.01, "position": 30.0}]

    with patch("agents.seo.rank_tracker.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=boundary_gsc)
        result = await RankTrackerAgent().run(ctx)

    assert result.data["quick_wins"] == 1
    assert result.data["ranking"] == 0


@pytest.mark.asyncio
async def test_previous_position_populated_from_history() -> None:
    """Previous position should come from latest rank_tracking row for that keyword."""
    rows = [_kw_row("kw-1", "ai marketing automation")]
    prev = [("kw-1", 7.5)]  # was position 7.5 last run
    db = _make_db(rows, prev_positions=prev)
    ctx = _make_ctx(db)

    with patch("agents.seo.rank_tracker.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await RankTrackerAgent().run(ctx)

    assert result.status == "success"
    # Verify the INSERT was called with previous_position param
    insert_calls = [
        c for c in db.execute.call_args_list
        if "INSERT INTO rank_tracking" in str(c[0][0])
    ]
    assert len(insert_calls) == 1
    insert_params = insert_calls[0][0][1]
    assert insert_params["previous_position"] == 7.5


@pytest.mark.asyncio
async def test_empty_keywords_returns_success() -> None:
    db = _make_db([])
    ctx = _make_ctx(db)

    with patch("agents.seo.rank_tracker.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await RankTrackerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total_tracked"] == 0
    assert "message" in result.data


@pytest.mark.asyncio
async def test_gsc_failure_falls_back_to_not_ranking() -> None:
    rows = [_kw_row("kw-1", "ai marketing automation")]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    with patch("agents.seo.rank_tracker.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(
            side_effect=Exception("GSC down")
        )
        result = await RankTrackerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total_tracked"] == 1
    assert result.data["not_ranking"] == 1
    assert result.data["gsc_rows_fetched"] == 0


@pytest.mark.asyncio
async def test_missing_site_url_returns_failed() -> None:
    db = _make_db([])
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={}, config={}, db=db, llm=MagicMock()
    )

    with patch("agents.seo.rank_tracker.settings") as mock_settings:
        mock_settings.gsc_site_url = ""
        result = await RankTrackerAgent().run(ctx)

    assert result.status == "failed"


@pytest.mark.asyncio
async def test_tokens_used_is_zero() -> None:
    rows = [_kw_row("kw-1", "ai marketing automation")]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    with patch("agents.seo.rank_tracker.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await RankTrackerAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == 0.0
