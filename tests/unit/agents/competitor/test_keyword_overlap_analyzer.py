"""Unit tests for KeywordOverlapAnalyzerAgent."""
from unittest.mock import AsyncMock, MagicMock

import pytest

import agents.competitor.keyword_overlap_analyzer  # noqa: F401

from agents.competitor.keyword_overlap_analyzer import KeywordOverlapAnalyzerAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_KEYWORDS = [
    ("kw-1", "ai marketing"),
    ("kw-2", "seo automation"),
    ("kw-3", "content strategy"),
]

_CONTENT = [
    ("cc-1", "https://competitor.com/blog/ai", "We use AI marketing to grow our brand with seo automation."),
    ("cc-2", "https://competitor.com/blog/seo", "Our content strategy focuses on organic search."),
    ("cc-3", "https://competitor.com/blog/other", "Completely unrelated text about plumbing."),
]


def _kw_row(id_: str, keyword: str) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, i: (id_, keyword)[i]
    return row


def _content_row(id_: str, url: str, body: str) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, i: (id_, url, body)[i]
    return row


def _make_db(kw_rows=None, content_rows=None) -> AsyncMock:
    kw_rows = kw_rows if kw_rows is not None else [
        _kw_row(id_, kw) for id_, kw in _KEYWORDS
    ]
    content_rows = content_rows if content_rows is not None else [
        _content_row(id_, url, body) for id_, url, body in _CONTENT
    ]

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM keywords" in sql:
            result.fetchall.return_value = kw_rows
        elif "FROM competitor_content" in sql and "SELECT id, url, body" in sql:
            result.fetchall.return_value = content_rows
        else:
            result.fetchall.return_value = []
            result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    return db


def _make_ctx(db: AsyncMock) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params={},
        config={},
        db=db,
        llm=MagicMock(),
    )


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_counts_matches_correctly() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    result = await KeywordOverlapAnalyzerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total_analyzed"] == 3
    assert result.data["keywords_checked"] == 3
    # cc-1 matches "ai marketing" + "seo automation" = 2
    # cc-2 matches "content strategy" = 1
    # cc-3 matches nothing = 0
    assert result.data["total_keyword_matches"] == 3
    assert db.flush.called


@pytest.mark.asyncio
async def test_all_rows_updated_regardless_of_match_count() -> None:
    """Even zero-match rows get their keywords_overlap updated."""
    db = _make_db()
    ctx = _make_ctx(db)

    await KeywordOverlapAnalyzerAgent().run(ctx)

    update_calls = [
        c for c in db.execute.call_args_list
        if "UPDATE competitor_content" in str(c[0][0])
    ]
    assert len(update_calls) == 3  # one UPDATE per content row


@pytest.mark.asyncio
async def test_match_is_case_insensitive() -> None:
    """Body text in mixed case should still match lowercase keywords."""
    content = [_content_row("cc-1", "https://x.com", "AI MARKETING is trending")]
    db = _make_db(content_rows=content)
    ctx = _make_ctx(db)

    result = await KeywordOverlapAnalyzerAgent().run(ctx)

    assert result.data["total_keyword_matches"] == 1


@pytest.mark.asyncio
async def test_update_called_with_correct_content_id() -> None:
    content = [_content_row("cc-99", "https://x.com", "ai marketing rocks")]
    db = _make_db(content_rows=content)
    ctx = _make_ctx(db)

    await KeywordOverlapAnalyzerAgent().run(ctx)

    update_calls = [
        c for c in db.execute.call_args_list
        if "UPDATE competitor_content" in str(c[0][0])
    ]
    assert update_calls[0][0][1]["id"] == "cc-99"


# ── Edge cases ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_keywords_returns_success_with_message() -> None:
    db = _make_db(kw_rows=[])
    ctx = _make_ctx(db)

    result = await KeywordOverlapAnalyzerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total_analyzed"] == 0
    assert "message" in result.data


@pytest.mark.asyncio
async def test_no_content_with_body_returns_success() -> None:
    db = _make_db(content_rows=[])
    ctx = _make_ctx(db)

    result = await KeywordOverlapAnalyzerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total_analyzed"] == 0
    assert "message" in result.data


@pytest.mark.asyncio
async def test_no_matches_still_writes_empty_list() -> None:
    content = [_content_row("cc-1", "https://x.com", "plumbing services in London")]
    db = _make_db(content_rows=content)
    ctx = _make_ctx(db)

    result = await KeywordOverlapAnalyzerAgent().run(ctx)

    assert result.data["total_keyword_matches"] == 0
    update_calls = [
        c for c in db.execute.call_args_list
        if "UPDATE competitor_content" in str(c[0][0])
    ]
    # Still updates the row with an empty array
    assert len(update_calls) == 1


# ── Tokens ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tokens_used_is_zero() -> None:
    db = _make_db()
    ctx = _make_ctx(db)

    result = await KeywordOverlapAnalyzerAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == 0.0
