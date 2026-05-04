"""Unit tests for ContentExtractorAgent."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.competitor.content_extractor  # noqa: F401 — triggers @register

from agents.competitor.content_extractor import ContentExtractorAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_OK_FETCH = {"title": "Test Page", "body": "some body text here", "word_count": 4, "status": "ok"}
_FAILED_FETCH = {"title": "", "body": "", "word_count": 0, "status": "failed"}
_SKIPPED_FETCH = {"title": "", "body": "", "word_count": 0, "status": "skipped"}


def _cc_row(id: str, url: str, domain: str) -> MagicMock:
    row = MagicMock()
    row.id = id
    row.url = url
    row.domain = domain
    return row


def _make_db(rows: list) -> AsyncMock:
    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        result.fetchall.return_value = rows if "FROM competitor_content" in sql else []
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
async def test_extracts_pages_successfully() -> None:
    rows = [
        _cc_row("id-1", "https://notion.so/page1", "notion.so"),
        _cc_row("id-2", "https://notion.so/page2", "notion.so"),
    ]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    with patch("agents.competitor.content_extractor.ContentFetchIntegration") as MockFetch:
        MockFetch.return_value.fetch_page = AsyncMock(return_value=_OK_FETCH)
        result = await ContentExtractorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total"] == 2
    assert result.data["extracted"] == 2
    assert result.data["failed"] == 0
    assert result.data["skipped"] == 0
    assert db.flush.called


@pytest.mark.asyncio
async def test_failed_fetch_increments_failed_count() -> None:
    rows = [_cc_row("id-1", "https://notion.so/page1", "notion.so")]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    with patch("agents.competitor.content_extractor.ContentFetchIntegration") as MockFetch:
        MockFetch.return_value.fetch_page = AsyncMock(return_value=_FAILED_FETCH)
        result = await ContentExtractorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total"] == 1
    assert result.data["extracted"] == 0
    assert result.data["failed"] == 1
    assert result.data["skipped"] == 0


@pytest.mark.asyncio
async def test_skipped_url_increments_skipped_count() -> None:
    """Non-HTML or non-http URLs return status=skipped; agent does not write to DB."""
    rows = [_cc_row("id-1", "https://notion.so/file.pdf", "notion.so")]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    with patch("agents.competitor.content_extractor.ContentFetchIntegration") as MockFetch:
        MockFetch.return_value.fetch_page = AsyncMock(return_value=_SKIPPED_FETCH)
        result = await ContentExtractorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total"] == 1
    assert result.data["extracted"] == 0
    assert result.data["failed"] == 0
    assert result.data["skipped"] == 1


@pytest.mark.asyncio
async def test_empty_queue_returns_success_with_zeros() -> None:
    """No unextracted rows → success with all counts at zero."""
    db = _make_db([])
    ctx = _make_ctx(db)

    with patch("agents.competitor.content_extractor.ContentFetchIntegration"):
        result = await ContentExtractorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total"] == 0
    assert result.data["extracted"] == 0
    assert "message" in result.data


@pytest.mark.asyncio
async def test_mixed_results_counted_correctly() -> None:
    rows = [
        _cc_row("id-1", "https://notion.so/ok", "notion.so"),
        _cc_row("id-2", "https://notion.so/fail", "notion.so"),
        _cc_row("id-3", "https://notion.so/skip.pdf", "notion.so"),
    ]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    fetch_responses = [_OK_FETCH, _FAILED_FETCH, _SKIPPED_FETCH]

    with patch("agents.competitor.content_extractor.ContentFetchIntegration") as MockFetch:
        MockFetch.return_value.fetch_page = AsyncMock(side_effect=fetch_responses)
        result = await ContentExtractorAgent().run(ctx)

    assert result.data["total"] == 3
    assert result.data["extracted"] == 1
    assert result.data["failed"] == 1
    assert result.data["skipped"] == 1


@pytest.mark.asyncio
async def test_competitor_ids_filter_in_query_params() -> None:
    """competitor_ids param must appear in the SELECT query parameters."""
    rows = [_cc_row("id-1", "https://notion.so/page", "notion.so")]
    db = _make_db(rows)
    ctx = _make_ctx(db, params={"competitor_ids": ["comp-1", "comp-2"]})

    with patch("agents.competitor.content_extractor.ContentFetchIntegration") as MockFetch:
        MockFetch.return_value.fetch_page = AsyncMock(return_value=_OK_FETCH)
        await ContentExtractorAgent().run(ctx)

    # call 0 = _create_run_record INSERT, call 1 = SELECT competitor_content
    select_params = db.execute.call_args_list[1][0][1]
    assert "cid_0" in select_params
    assert select_params["cid_0"] == "comp-1"


@pytest.mark.asyncio
async def test_limit_param_passed_to_query() -> None:
    db = _make_db([])
    ctx = _make_ctx(db, params={"limit": 25})

    with patch("agents.competitor.content_extractor.ContentFetchIntegration"):
        await ContentExtractorAgent().run(ctx)

    select_params = db.execute.call_args_list[1][0][1]
    assert select_params["limit"] == 25


@pytest.mark.asyncio
async def test_tokens_used_is_zero() -> None:
    """No LLM calls — tokens and cost must always be zero."""
    rows = [_cc_row("id-1", "https://notion.so/page", "notion.so")]
    db = _make_db(rows)
    ctx = _make_ctx(db)

    with patch("agents.competitor.content_extractor.ContentFetchIntegration") as MockFetch:
        MockFetch.return_value.fetch_page = AsyncMock(return_value=_OK_FETCH)
        result = await ContentExtractorAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == 0.0
