"""Unit tests for SentimentFilterAgent and its pure helpers."""
from unittest.mock import AsyncMock, MagicMock

import pytest

import agents.sentiment.sentiment_filter  # noqa: F401 — triggers @register

from agents.sentiment.sentiment_filter import (
    SentimentFilterAgent,
    _content_hash,
    _detect_language,
    _is_relevant,
    _normalize,
)
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"


def _make_ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params=params or {},
        config={},
        db=db,
        llm=MagicMock(),
    )


def _raw_mention(
    body: str = "This scheme has helped many farmers in Madurai district.",
    title: str = "",
    scheme_hint: list | None = None,
    district_hint: list | None = None,
) -> dict:
    return {
        "id": "aaaaaaaa-0000-0000-0000-000000000001",
        "body": body,
        "title": title,
        "source": "newsapi",
        "source_identifier": "the-hindu",
        "url": "https://example.com/1",
        "published_at": None,
        "engagement_raw": {},
        "scheme_hint": scheme_hint or ["amma_scheme"],
        "district_hint": district_hint or ["madurai"],
    }


def _make_db(raw_mentions: list, duplicate: bool = False, weight: float | None = None) -> AsyncMock:
    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM raw_mentions" in sql:
            rows = []
            for m in raw_mentions:
                row = MagicMock()
                row._mapping = m
                rows.append(row)
            result.fetchall.return_value = rows
        elif "FROM relevant_mentions" in sql:
            result.fetchone.return_value = (1,) if duplicate else None
        elif "FROM source_credibility" in sql:
            result.fetchone.return_value = (weight,) if weight is not None else None
        else:
            result.fetchall.return_value = []
            result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    return db


# ── Pure function tests ───────────────────────────────────────────────────────

def test_normalize_strips_html() -> None:
    result = _normalize("<p>Hello <b>world</b></p>")
    assert "<" not in result
    assert "Hello" in result
    assert "world" in result


def test_normalize_collapses_whitespace() -> None:
    result = _normalize("  too   many    spaces  ")
    assert "  " not in result
    assert result == "too many spaces"


def test_normalize_empty_string() -> None:
    assert _normalize("") == ""


def test_detect_language_english() -> None:
    lang, conf = _detect_language("The smart city scheme in Madurai has improved water supply.")
    assert lang == "en"
    assert conf > 0.0


def test_detect_language_unknown_for_short_text() -> None:
    lang, conf = _detect_language("hi")
    assert lang == "unknown"
    assert conf == 0.0


def test_detect_language_unknown_on_empty() -> None:
    lang, conf = _detect_language("")
    assert lang == "unknown"


def test_is_relevant_scheme_keyword_match() -> None:
    assert _is_relevant("amma scheme benefits farmers", "amma scheme", "") is True


def test_is_relevant_district_match() -> None:
    assert _is_relevant("news from madurai today", "", "madurai") is True


def test_is_relevant_no_filter_always_true() -> None:
    assert _is_relevant("anything goes here", "", "") is True


def test_is_relevant_miss_returns_false() -> None:
    assert _is_relevant("unrelated sports news", "amma scheme", "madurai") is False


def test_is_relevant_short_words_not_matched() -> None:
    # Words with len <= 3 are skipped by the scheme split logic
    assert _is_relevant("the of in", "the", "") is False


def test_content_hash_deterministic() -> None:
    h1 = _content_hash("scheme water supply madurai")
    h2 = _content_hash("scheme water supply madurai")
    assert h1 == h2


def test_content_hash_case_insensitive() -> None:
    h1 = _content_hash("SCHEME WATER")
    h2 = _content_hash("scheme water")
    assert h1 == h2


def test_content_hash_different_text() -> None:
    h1 = _content_hash("water supply")
    h2 = _content_hash("road repair")
    assert h1 != h2


# ── Agent: body too short → filtered_out ─────────────────────────────────────

@pytest.mark.asyncio
async def test_short_body_filtered_out() -> None:
    raw = _raw_mention(body="Short.")
    db = _make_db([raw])
    result = await SentimentFilterAgent().run(_make_ctx(db))
    assert result.status == "success"
    assert result.data["filtered_out"] == 1
    assert result.data["filtered_in"] == 0


# ── Agent: duplicate → marked duplicate ──────────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_content_skipped() -> None:
    raw = _raw_mention()
    db = _make_db([raw], duplicate=True)
    result = await SentimentFilterAgent().run(_make_ctx(db))
    assert result.status == "success"
    assert result.data["duplicate"] == 1
    assert result.data["filtered_in"] == 0


# ── Agent: irrelevant content → filtered_out ─────────────────────────────────

@pytest.mark.asyncio
async def test_irrelevant_mention_filtered_out() -> None:
    raw = _raw_mention(
        body="Cricket match scores from yesterday evening in Chennai stadium.",
        scheme_hint=[],
        district_hint=[],
    )
    db = _make_db([raw])
    ctx = _make_ctx(db, params={"scheme_key": "amma_scheme", "district_key": "madurai"})
    result = await SentimentFilterAgent().run(ctx)
    assert result.status == "success"
    assert result.data["filtered_out"] == 1


# ── Agent: happy path → filtered_in ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_relevant_mention_filtered_in() -> None:
    raw = _raw_mention()
    db = _make_db([raw], duplicate=False)
    ctx = _make_ctx(db, params={"scheme_key": "amma_scheme", "district_key": "madurai"})
    result = await SentimentFilterAgent().run(ctx)
    assert result.status == "success"
    assert result.data["filtered_in"] == 1
    assert result.data["filtered_out"] == 0
    assert result.data["duplicate"] == 0


# ── Agent: empty pending → success with zeros ─────────────────────────────────

@pytest.mark.asyncio
async def test_no_pending_returns_success() -> None:
    db = _make_db([])
    result = await SentimentFilterAgent().run(_make_ctx(db))
    assert result.status == "success"
    assert result.data["processed"] == 0


# ── Agent: source weight looked up ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_source_weight_fallback_to_one() -> None:
    raw = _raw_mention()
    db = _make_db([raw], weight=None)
    result = await SentimentFilterAgent().run(_make_ctx(db))
    assert result.status == "success"
    # No crash — weight defaulted to 1.0
