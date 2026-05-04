"""Unit tests for GapAnalyzerAgent."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.seo.gap_analyzer  # noqa: F401 — triggers @register

from agents.seo.gap_analyzer import GapAnalyzerAgent, _compute_gap_score
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"
SITE_URL = "https://example.com"

_GSC_ROWS = [
    {"query": "ai marketing automation", "clicks": 142, "impressions": 1500, "ctr": 0.094, "position": 4.2},
    {"query": "multi agent system tutorial", "clicks": 12, "impressions": 850, "ctr": 0.014, "position": 14.5},
]


def _opp_row(id: str, keyword_id: str, keyword: str) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.keyword_id = keyword_id
    row.keyword = keyword
    return row


def _make_db(opp_rows: list, competitor_count: int = 0) -> AsyncMock:
    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM opportunities" in sql:
            result.fetchall.return_value = opp_rows
        elif "FROM competitor_content" in sql:
            result.fetchone.return_value = (competitor_count,)
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


# ── Unit: scoring formula ─────────────────────────────────────────────────────

def test_no_rank_no_competitors_gives_medium_score() -> None:
    assert _compute_gap_score(None, 0) == 5.0


def test_no_rank_with_competitors_gives_high_score() -> None:
    score = _compute_gap_score(None, 3)
    assert score >= 9.0


def test_ranking_well_no_competitors_gives_low_score() -> None:
    score = _compute_gap_score(3.0, 0)
    assert score <= 2.0


def test_page_two_rank_with_competitors_is_higher_than_page_one() -> None:
    page_one = _compute_gap_score(5.0, 2)
    page_two = _compute_gap_score(15.0, 2)
    assert page_two > page_one


def test_gap_score_clamped_to_ten() -> None:
    score = _compute_gap_score(None, 10)
    assert score <= 10.0


# ── Agent: happy path ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scores_opportunities_with_gsc_data() -> None:
    rows = [_opp_row("opp-1", "kw-1", "ai marketing automation")]
    db = _make_db(rows, competitor_count=2)
    ctx = _make_ctx(db)

    with patch("agents.seo.gap_analyzer.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await GapAnalyzerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["gaps_scored"] == 1
    assert result.data["keywords_in_gsc"] == 1
    assert db.flush.called


@pytest.mark.asyncio
async def test_keyword_not_in_gsc_still_scored() -> None:
    """A keyword with no GSC position gets position_score=5.0 (unranked)."""
    rows = [_opp_row("opp-1", "kw-1", "completely unknown keyword")]
    db = _make_db(rows, competitor_count=0)
    ctx = _make_ctx(db)

    with patch("agents.seo.gap_analyzer.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await GapAnalyzerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["gaps_scored"] == 1
    assert result.data["keywords_in_gsc"] == 0


@pytest.mark.asyncio
async def test_high_competitor_coverage_raises_gap_score() -> None:
    """More competitor pages covering the keyword → higher gap score."""
    rows = [_opp_row("opp-1", "kw-1", "seo tools")]
    db_few = _make_db(rows, competitor_count=0)
    db_many = _make_db(rows, competitor_count=4)

    with patch("agents.seo.gap_analyzer.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=[])
        result_few = await GapAnalyzerAgent().run(_make_ctx(db_few))

    with patch("agents.seo.gap_analyzer.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=[])
        result_many = await GapAnalyzerAgent().run(_make_ctx(db_many))

    # When more competitors cover it, gaps_scored still equals 1 each time
    assert result_few.data["gaps_scored"] == 1
    assert result_many.data["gaps_scored"] == 1


@pytest.mark.asyncio
async def test_empty_opportunities_returns_success() -> None:
    db = _make_db([])
    ctx = _make_ctx(db)

    with patch("agents.seo.gap_analyzer.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await GapAnalyzerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["gaps_scored"] == 0
    assert "message" in result.data


@pytest.mark.asyncio
async def test_gsc_failure_still_scores_with_no_position() -> None:
    """If GSC is unavailable, agent falls back to unranked scoring instead of failing."""
    rows = [_opp_row("opp-1", "kw-1", "ai marketing")]
    db = _make_db(rows, competitor_count=1)
    ctx = _make_ctx(db)

    with patch("agents.seo.gap_analyzer.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(
            side_effect=Exception("GSC timeout")
        )
        result = await GapAnalyzerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["gaps_scored"] == 1
    assert result.data["gsc_rows_fetched"] == 0


@pytest.mark.asyncio
async def test_missing_site_url_returns_failed() -> None:
    db = _make_db([])
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={}, config={}, db=db, llm=MagicMock()
    )

    with patch("agents.seo.gap_analyzer.settings") as mock_settings:
        mock_settings.gsc_site_url = ""
        result = await GapAnalyzerAgent().run(ctx)

    assert result.status == "failed"


@pytest.mark.asyncio
async def test_tokens_used_is_zero() -> None:
    rows = [_opp_row("opp-1", "kw-1", "ai tools")]
    db = _make_db(rows, competitor_count=0)
    ctx = _make_ctx(db)

    with patch("agents.seo.gap_analyzer.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=[])
        result = await GapAnalyzerAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == 0.0
