"""Unit tests for AeoScannerAgent.

SerpScraperIntegration is always mocked — no real Google requests.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.seo.aeo_scanner  # noqa: F401

from agents.seo.aeo_scanner import AeoScannerAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

KW_ID_1 = str(uuid.uuid4())
KW_ID_2 = str(uuid.uuid4())
KW_ID_3 = str(uuid.uuid4())

_KW_ROWS = [
    (KW_ID_1, "ai marketing automation"),
    (KW_ID_2, "seo keyword research tool"),
    (KW_ID_3, "content marketing strategy"),
]

# Canonical SERP results for each mock scenario
_SERP_AI_OVERVIEW = {
    "found": True, "blocked": False,
    "ai_overview": True, "featured_snippet": False,
    "paa_count": 3, "organic_position": 4,
}
_SERP_FEATURED_SNIPPET = {
    "found": True, "blocked": False,
    "ai_overview": False, "featured_snippet": True,
    "paa_count": 2, "organic_position": 1,
}
_SERP_PLAIN = {
    "found": True, "blocked": False,
    "ai_overview": False, "featured_snippet": False,
    "paa_count": 0, "organic_position": 7,
}
_SERP_BLOCKED = {
    "found": False, "blocked": True,
    "ai_overview": False, "featured_snippet": False,
    "paa_count": 0, "organic_position": None,
}
_SERP_NOT_FOUND = {
    "found": False, "blocked": False,
    "ai_overview": False, "featured_snippet": False,
    "paa_count": 0, "organic_position": None,
}


def _kw_row(row_id: str, keyword: str) -> MagicMock:
    r = MagicMock()
    r.__getitem__ = lambda self, i: (row_id, keyword)[i]
    return r


def _make_db(kw_rows: list | None = None) -> AsyncMock:
    rows = [_kw_row(*r) for r in (_KW_ROWS if kw_rows is None else kw_rows)]
    mock_result = MagicMock()
    mock_result.rowcount = 1
    mock_result.fetchall.return_value = rows

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params={**(params or {})},
        config={},
        db=db,
        llm=MagicMock(),
    )


def _patch_scraper(side_effect: list | None = None, return_value: dict | None = None):
    """Patch SerpScraperIntegration.scrape_serp.

    Pass side_effect for per-call responses, or return_value for a constant.
    """
    if side_effect is not None:
        mock = AsyncMock(side_effect=side_effect)
    else:
        mock = AsyncMock(return_value=return_value or _SERP_PLAIN)

    return patch(
        "agents.seo.aeo_scanner.SerpScraperIntegration",
        **{"return_value.scrape_serp": mock},
    )


def _patch_sleep():
    """Suppress asyncio.sleep delays in tests."""
    return patch("agents.seo.aeo_scanner.asyncio.sleep", new=AsyncMock())


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_successful_run_returns_success() -> None:
    db = _make_db()
    with _patch_scraper(), _patch_sleep():
        result = await AeoScannerAgent().run(_ctx(db))
    assert result.status == "success"


async def test_total_matches_keywords_scanned() -> None:
    db = _make_db()
    with _patch_scraper(), _patch_sleep():
        result = await AeoScannerAgent().run(_ctx(db))
    assert result.data["total"] == 3


async def test_ai_overview_count_correct() -> None:
    db = _make_db()
    # First kw returns AI overview, rest don't
    responses = [_SERP_AI_OVERVIEW, _SERP_PLAIN, _SERP_PLAIN]
    with _patch_scraper(side_effect=responses), _patch_sleep():
        result = await AeoScannerAgent().run(_ctx(db))
    assert result.data["ai_overview_count"] == 1


async def test_featured_snippet_count_correct() -> None:
    db = _make_db()
    responses = [_SERP_FEATURED_SNIPPET, _SERP_FEATURED_SNIPPET, _SERP_PLAIN]
    with _patch_scraper(side_effect=responses), _patch_sleep():
        result = await AeoScannerAgent().run(_ctx(db))
    assert result.data["featured_snippet_count"] == 2


async def test_blocked_count_correct() -> None:
    db = _make_db()
    responses = [_SERP_PLAIN, _SERP_BLOCKED, _SERP_BLOCKED]
    with _patch_scraper(side_effect=responses), _patch_sleep():
        result = await AeoScannerAgent().run(_ctx(db))
    assert result.data["blocked_count"] == 2


async def test_zero_tokens_no_llm() -> None:
    db = _make_db()
    with _patch_scraper(), _patch_sleep():
        result = await AeoScannerAgent().run(_ctx(db))
    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


# ── DB writes ─────────────────────────────────────────────────────────────────

async def test_upsert_called_once_per_keyword() -> None:
    db = _make_db()
    with _patch_scraper(), _patch_sleep():
        result = await AeoScannerAgent().run(_ctx(db))
    aeo_inserts = [
        c for c in db.execute.call_args_list
        if "INSERT INTO aeo_results" in str(c[0][0])
    ]
    assert len(aeo_inserts) == result.data["total"]


async def test_correct_keyword_id_written_to_db() -> None:
    db = _make_db(kw_rows=[(KW_ID_1, "ai marketing")])
    with _patch_scraper(), _patch_sleep():
        await AeoScannerAgent().run(_ctx(db))
    aeo_inserts = [
        c for c in db.execute.call_args_list
        if "INSERT INTO aeo_results" in str(c[0][0])
    ]
    assert aeo_inserts[0][0][1]["keyword_id"] == KW_ID_1


async def test_ai_overview_flag_passed_to_db() -> None:
    db = _make_db(kw_rows=[(KW_ID_1, "some keyword")])
    with _patch_scraper(return_value=_SERP_AI_OVERVIEW), _patch_sleep():
        await AeoScannerAgent().run(_ctx(db))
    aeo_inserts = [
        c for c in db.execute.call_args_list
        if "INSERT INTO aeo_results" in str(c[0][0])
    ]
    assert aeo_inserts[0][0][1]["ai_overview"] is True


async def test_flush_called_after_all_writes() -> None:
    db = _make_db()
    with _patch_scraper(), _patch_sleep():
        await AeoScannerAgent().run(_ctx(db))
    assert db.flush.call_count >= 1


async def test_blocked_status_written_to_db() -> None:
    db = _make_db(kw_rows=[(KW_ID_1, "test keyword")])
    with _patch_scraper(return_value=_SERP_BLOCKED), _patch_sleep():
        await AeoScannerAgent().run(_ctx(db))
    aeo_inserts = [
        c for c in db.execute.call_args_list
        if "INSERT INTO aeo_results" in str(c[0][0])
    ]
    assert aeo_inserts[0][0][1]["status"] == "blocked"


# ── batch_size cap ────────────────────────────────────────────────────────────

async def test_batch_size_limits_keywords_scanned() -> None:
    db = _make_db()  # 3 kw rows returned by DB
    with _patch_scraper(), _patch_sleep():
        result = await AeoScannerAgent().run(_ctx(db, {"batch_size": 2}))
    assert result.data["total"] <= 2


# ── keyword_ids param ─────────────────────────────────────────────────────────

async def test_keyword_ids_param_used_when_provided() -> None:
    """When keyword_ids are given, the id-based query path is used."""
    db = _make_db(kw_rows=[(KW_ID_1, "ai marketing")])
    with _patch_scraper(), _patch_sleep():
        result = await AeoScannerAgent().run(
            _ctx(db, {"keyword_ids": [KW_ID_1]})
        )
    assert result.status == "success"
    # Verify the ANY(:ids) query was used (not the 'validated' query)
    kw_queries = [
        c for c in db.execute.call_args_list
        if "ANY" in str(c[0][0]) and "keywords" in str(c[0][0])
    ]
    assert len(kw_queries) >= 1


# ── Empty keyword list ────────────────────────────────────────────────────────

async def test_no_keywords_returns_success_zero() -> None:
    db = _make_db(kw_rows=[])
    with _patch_scraper(), _patch_sleep():
        result = await AeoScannerAgent().run(_ctx(db))
    assert result.status == "success"
    assert result.data["total"] == 0
    assert "message" in result.data


# ── Circuit breaker open ──────────────────────────────────────────────────────

async def test_circuit_open_all_blocked() -> None:
    """When every scrape returns blocked=True, blocked_count == total queries attempted."""
    db = _make_db(kw_rows=[(KW_ID_1, "test"), (KW_ID_2, "seo")])
    responses = [_SERP_BLOCKED, _SERP_BLOCKED]
    with _patch_scraper(side_effect=responses), _patch_sleep():
        result = await AeoScannerAgent().run(_ctx(db))
    assert result.data["blocked_count"] == 2
    assert result.data["total"] == 2   # blocked rows still written
    assert result.status == "success"


# ── SERP parsing ──────────────────────────────────────────────────────────────

async def test_serp_parser_ai_overview_detected() -> None:
    """_parse_serp_html detects AI Overview div by class TzHB6b."""
    from integrations.serp_scraper import _parse_serp_html

    html = '<html><body><div class="TzHB6b">AI overview text</div></body></html>'
    result = _parse_serp_html(html)
    assert result["ai_overview"] is True


async def test_serp_parser_featured_snippet_detected() -> None:
    from integrations.serp_scraper import _parse_serp_html

    html = '<html><body><div class="V3FYCf">Featured answer</div></body></html>'
    result = _parse_serp_html(html)
    assert result["featured_snippet"] is True


async def test_serp_parser_paa_counted() -> None:
    from integrations.serp_scraper import _parse_serp_html

    html = (
        '<html><body>'
        '<div class="related-question-pair">Q1</div>'
        '<div class="related-question-pair">Q2</div>'
        '<div class="related-question-pair">Q3</div>'
        '</body></html>'
    )
    result = _parse_serp_html(html)
    assert result["paa_count"] == 3


async def test_serp_parser_empty_html_returns_false() -> None:
    from integrations.serp_scraper import _parse_serp_html

    result = _parse_serp_html("<html><body></body></html>")
    assert result["ai_overview"] is False
    assert result["featured_snippet"] is False
    assert result["paa_count"] == 0
