"""Unit tests for TopicDiscoveryAgent."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.seo.topic_discovery  # noqa: F401

from agents.seo.topic_discovery import TopicDiscoveryAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_SEED = "content marketing"

# Fake data each source returns
_PYTRENDS_RESULTS = [
    {"topic": "content marketing strategy", "source": "pytrends_top"},
    {"topic": "content marketing trends 2024", "source": "pytrends_rising"},
]
_SUGGEST_RESULTS = [
    "content marketing tools",
    "content marketing examples",
    "content marketing ROI",
]
_REDDIT_RESULTS = [
    {"topic": "How we 10x'd organic traffic with content marketing", "source": "reddit"},
    {"topic": "Content marketing case study: B2B SaaS", "source": "reddit"},
]


def _make_db() -> AsyncMock:
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 1
    db.execute = AsyncMock(return_value=mock_result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params={"seed_keyword": _SEED, **(params or {})},
        config={},
        db=db,
        llm=MagicMock(),
    )


def _patch_pytrends(results=None):
    r = results if results is not None else _PYTRENDS_RESULTS
    return patch(
        "agents.seo.topic_discovery._fetch_pytrends_sync",
        return_value=r,
    )


def _patch_suggest(results=None):
    r = results if results is not None else _SUGGEST_RESULTS
    return patch(
        "agents.seo.topic_discovery._fetch_google_suggest",
        new=AsyncMock(return_value=r),
    )


def _patch_reddit(results=None):
    r = results if results is not None else _REDDIT_RESULTS
    return patch(
        "agents.seo.topic_discovery._fetch_reddit",
        new=AsyncMock(return_value=r),
    )


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_successful_run_returns_success() -> None:
    db = _make_db()
    with _patch_pytrends(), _patch_suggest(), _patch_reddit():
        result = await TopicDiscoveryAgent().run(_ctx(db))
    assert result.status == "success"


async def test_topics_written_count_matches_unique_topics() -> None:
    db = _make_db()
    with _patch_pytrends(), _patch_suggest(), _patch_reddit():
        result = await TopicDiscoveryAgent().run(_ctx(db))
    # 2 pytrends + 3 suggest + 2 reddit = 7 unique topics
    assert result.data["topics_written"] == 7


async def test_seed_keyword_echoed_in_result() -> None:
    db = _make_db()
    with _patch_pytrends(), _patch_suggest(), _patch_reddit():
        result = await TopicDiscoveryAgent().run(_ctx(db))
    assert result.data["seed_keyword"] == _SEED


async def test_db_execute_called_once_per_topic() -> None:
    db = _make_db()
    with _patch_pytrends(), _patch_suggest(), _patch_reddit():
        result = await TopicDiscoveryAgent().run(_ctx(db))
    topic_inserts = [
        c for c in db.execute.call_args_list
        if "INSERT INTO topics" in str(c[0][0])
    ]
    assert len(topic_inserts) == result.data["topics_written"]


async def test_db_flush_called_after_writes() -> None:
    db = _make_db()
    with _patch_pytrends(), _patch_suggest(), _patch_reddit():
        await TopicDiscoveryAgent().run(_ctx(db))
    assert db.flush.call_count >= 1


async def test_zero_tokens_no_llm() -> None:
    db = _make_db()
    with _patch_pytrends(), _patch_suggest(), _patch_reddit():
        result = await TopicDiscoveryAgent().run(_ctx(db))
    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


# ── Scoring ───────────────────────────────────────────────────────────────────

def _topic_insert_calls(db: AsyncMock) -> list:
    return [
        c for c in db.execute.call_args_list
        if "INSERT INTO topics" in str(c[0][0])
    ]


async def test_pytrends_rising_scores_8() -> None:
    """pytrends_rising topics should be scored 8.0."""
    db = _make_db()
    rising_only = [{"topic": "ai content tools", "source": "pytrends_rising"}]
    with _patch_pytrends(rising_only), _patch_suggest([]), _patch_reddit([]):
        await TopicDiscoveryAgent().run(_ctx(db))
    call_kwargs = _topic_insert_calls(db)[0][0][1]
    assert call_kwargs["score"] == 8.0


async def test_pytrends_top_scores_6() -> None:
    db = _make_db()
    top_only = [{"topic": "content strategy", "source": "pytrends_top"}]
    with _patch_pytrends(top_only), _patch_suggest([]), _patch_reddit([]):
        await TopicDiscoveryAgent().run(_ctx(db))
    call_kwargs = _topic_insert_calls(db)[0][0][1]
    assert call_kwargs["score"] == 6.0


async def test_google_suggest_scores_5() -> None:
    db = _make_db()
    with _patch_pytrends([]), _patch_suggest(["content marketing guide"]), _patch_reddit([]):
        await TopicDiscoveryAgent().run(_ctx(db))
    call_kwargs = _topic_insert_calls(db)[0][0][1]
    assert call_kwargs["score"] == 5.0


async def test_reddit_scores_4() -> None:
    db = _make_db()
    reddit_only = [{"topic": "Some reddit post title", "source": "reddit"}]
    with _patch_pytrends([]), _patch_suggest([]), _patch_reddit(reddit_only):
        await TopicDiscoveryAgent().run(_ctx(db))
    call_kwargs = _topic_insert_calls(db)[0][0][1]
    assert call_kwargs["score"] == 4.0


# ── Deduplication ─────────────────────────────────────────────────────────────

async def test_duplicate_topics_across_sources_deduped() -> None:
    """Same topic from two sources should only be written once."""
    db = _make_db()
    same_topic = [{"topic": "content marketing guide", "source": "pytrends_top"}]
    same_suggest = ["content marketing guide"]  # exact duplicate
    with _patch_pytrends(same_topic), _patch_suggest(same_suggest), _patch_reddit([]):
        result = await TopicDiscoveryAgent().run(_ctx(db))
    assert result.data["topics_written"] == 1


async def test_seed_keyword_itself_excluded() -> None:
    """The seed keyword is not written as a topic (it's trivially related to itself)."""
    db = _make_db()
    with _patch_pytrends([]), _patch_suggest([_SEED]), _patch_reddit([]):
        result = await TopicDiscoveryAgent().run(_ctx(db))
    assert result.data["topics_written"] == 0


async def test_max_topics_caps_output() -> None:
    db = _make_db()
    many_suggest = [f"topic {i}" for i in range(50)]
    with _patch_pytrends([]), _patch_suggest(many_suggest), _patch_reddit([]):
        result = await TopicDiscoveryAgent().run(
            _ctx(db, {"seed_keyword": _SEED, "max_topics": 5})
        )
    assert result.data["topics_written"] == 5


# ── Per-source graceful degradation ──────────────────────────────────────────

async def test_pytrends_failure_still_returns_success() -> None:
    db = _make_db()
    with (
        patch("agents.seo.topic_discovery._fetch_pytrends_sync", side_effect=Exception("rate limited")),
        _patch_suggest(),
        _patch_reddit(),
    ):
        result = await TopicDiscoveryAgent().run(_ctx(db))
    assert result.status == "success"
    assert result.data["topics_written"] > 0


async def test_suggest_failure_still_returns_success() -> None:
    db = _make_db()
    with (
        _patch_pytrends(),
        patch("agents.seo.topic_discovery._fetch_google_suggest", new=AsyncMock(side_effect=Exception("timeout"))),
        _patch_reddit(),
    ):
        result = await TopicDiscoveryAgent().run(_ctx(db))
    assert result.status == "success"
    assert result.data["topics_written"] > 0


async def test_reddit_failure_still_returns_success() -> None:
    db = _make_db()
    with (
        _patch_pytrends(),
        _patch_suggest(),
        patch("agents.seo.topic_discovery._fetch_reddit", new=AsyncMock(side_effect=Exception("503"))),
    ):
        result = await TopicDiscoveryAgent().run(_ctx(db))
    assert result.status == "success"
    assert result.data["topics_written"] > 0


async def test_all_sources_fail_returns_success_with_zero() -> None:
    db = _make_db()
    with (
        patch("agents.seo.topic_discovery._fetch_pytrends_sync", side_effect=Exception("x")),
        patch("agents.seo.topic_discovery._fetch_google_suggest", new=AsyncMock(side_effect=Exception("x"))),
        patch("agents.seo.topic_discovery._fetch_reddit", new=AsyncMock(side_effect=Exception("x"))),
    ):
        result = await TopicDiscoveryAgent().run(_ctx(db))
    assert result.status == "success"
    assert result.data["topics_written"] == 0


# ── Missing param ─────────────────────────────────────────────────────────────

async def test_missing_seed_returns_failed() -> None:
    db = _make_db()
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={}, config={}, db=db, llm=MagicMock()
    )
    result = await TopicDiscoveryAgent().run(ctx)
    assert result.status == "failed"
    assert "seed_keyword" in (result.error or "")
