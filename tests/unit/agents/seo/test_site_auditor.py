"""Unit tests for SiteAuditorAgent."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.seo.site_auditor  # noqa: F401

from agents.seo.site_auditor import SiteAuditorAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"
SITE_URL = "https://example.com"

_GSC_ROWS = [
    {"query": "ai marketing", "clicks": 50, "impressions": 500, "ctr": 0.1, "position": 4.2},
    {"query": "seo tools", "clicks": 10, "impressions": 300, "ctr": 0.033, "position": 18.5},
]

# rank_tracking snapshots: (status, position)
_RANK_ROWS = [
    ("ranking", 4.2),
    ("quick_win", 18.5),
    ("quick_win", 22.1),
    ("not_ranking", None),
    ("not_ranking", None),
]


def _make_db(rank_rows=None) -> AsyncMock:
    rank_rows = rank_rows if rank_rows is not None else _RANK_ROWS

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM rank_tracking" in sql:
            result.fetchall.return_value = rank_rows
        elif "INSERT INTO site_audits" in sql:
            result.fetchone.return_value = MagicMock()
            result.fetchall.return_value = []
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


# ── Aggregation ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_counts_by_status_correct() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    with patch("agents.seo.site_auditor.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await SiteAuditorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["ranking"] == 1
    assert result.data["quick_wins"] == 2
    assert result.data["not_ranking"] == 2
    assert result.data["gsc_rows_fetched"] == 2


@pytest.mark.asyncio
async def test_avg_position_computed_correctly() -> None:
    # positions: 4.2, 18.5, 22.1 — two not_ranking rows have None position
    db = _make_db()
    ctx = _make_ctx(db)

    with patch("agents.seo.site_auditor.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await SiteAuditorAgent().run(ctx)

    expected_avg = round((4.2 + 18.5 + 22.1) / 3, 1)
    assert result.data["avg_position"] == expected_avg


@pytest.mark.asyncio
async def test_avg_position_none_when_no_ranked_keywords() -> None:
    rank_rows = [("not_ranking", None), ("not_ranking", None)]
    db = _make_db(rank_rows=rank_rows)
    ctx = _make_ctx(db)

    with patch("agents.seo.site_auditor.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=[])
        result = await SiteAuditorAgent().run(ctx)

    assert result.data["avg_position"] is None


@pytest.mark.asyncio
async def test_empty_rank_tracking_returns_zeros() -> None:
    db = _make_db(rank_rows=[])
    ctx = _make_ctx(db)

    with patch("agents.seo.site_auditor.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await SiteAuditorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["ranking"] == 0
    assert result.data["quick_wins"] == 0
    assert result.data["not_ranking"] == 0


# ── DB write ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inserts_one_audit_row() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    with patch("agents.seo.site_auditor.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        await SiteAuditorAgent().run(ctx)

    insert_calls = [
        c for c in db.execute.call_args_list
        if "INSERT INTO site_audits" in str(c[0][0])
    ]
    assert len(insert_calls) == 1
    assert insert_calls[0][0][1]["org_id"] == ORG_ID
    assert insert_calls[0][0][1]["site_url"] == SITE_URL
    assert db.flush.called


# ── GSC failure ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gsc_failure_falls_back_to_zero_gsc_rows() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    with patch("agents.seo.site_auditor.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(
            side_effect=Exception("GSC down")
        )
        result = await SiteAuditorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["gsc_rows_fetched"] == 0


# ── Missing site_url ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_site_url_returns_failed() -> None:
    db = _make_db()
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={}, config={}, db=db, llm=MagicMock()
    )

    with patch("agents.seo.site_auditor.settings") as mock_settings:
        mock_settings.gsc_site_url = ""
        result = await SiteAuditorAgent().run(ctx)

    assert result.status == "failed"


# ── Tokens ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tokens_used_is_zero() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    with patch("agents.seo.site_auditor.GoogleSearchConsoleIntegration") as MockGSC:
        MockGSC.return_value.get_search_analytics = AsyncMock(return_value=_GSC_ROWS)
        result = await SiteAuditorAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == 0.0
