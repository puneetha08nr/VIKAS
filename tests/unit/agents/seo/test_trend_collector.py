"""Unit tests for TrendCollectorAgent — 5-tier fallback."""
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.seo.trend_collector  # noqa: F401 — triggers @register

from agents.seo.trend_collector import (
    TrendCollectorAgent,
    _compute_momentum,
    _fetch_trends_sync,
    _google_suggest_momentum,
)
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_TRACE = json.loads(
    (
        pathlib.Path(__file__).parent.parent.parent.parent
        / "golden_traces"
        / "trend_collector_trace.json"
    ).read_text()
)


# ── DB mock factory ───────────────────────────────────────────────────────────

def _make_db(validated_keywords: list[str] | None = None) -> AsyncMock:
    kw_rows = [(kw,) for kw in (validated_keywords or [])]

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        result.fetchall.return_value = kw_rows if "FROM keywords" in sql else []
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


# ── _compute_momentum unit tests ──────────────────────────────────────────────

def test_flat_trend_returns_five() -> None:
    assert _compute_momentum([50.0] * 13) == 5.0


def test_rising_trend_returns_above_five() -> None:
    assert _compute_momentum([20.0] * 10 + [60.0, 70.0, 80.0]) > 5.0


def test_falling_trend_returns_below_five() -> None:
    assert _compute_momentum([80.0] * 10 + [20.0, 10.0, 5.0]) < 5.0


def test_empty_values_returns_five() -> None:
    assert _compute_momentum([]) == 5.0


def test_momentum_capped_at_ten() -> None:
    assert _compute_momentum([1.0] + [100.0] * 10) <= 10.0


def test_momentum_floored_at_zero() -> None:
    assert _compute_momentum([100.0] * 10 + [0.0, 0.0, 0.0]) >= 0.0


def test_dormant_keyword_any_interest_scores_above_zero() -> None:
    values = [0.0] * 10 + [50.0, 60.0, 70.0]
    assert _compute_momentum(values) > 0.0


# ── _fetch_trends_sync — only returns keywords with real data ─────────────────

def test_fetch_trends_sync_omits_keywords_with_no_df_column() -> None:
    """Keywords not in the dataframe are omitted so they fall through to Tier 2."""
    import pandas as pd

    mock_df = pd.DataFrame({"ai marketing": [50, 60, 70, 80]})
    mock_pt = MagicMock()
    mock_pt.interest_over_time.return_value = mock_df

    with patch("pytrends.request.TrendReq", return_value=mock_pt):
        signals = _fetch_trends_sync(["ai marketing", "missing keyword"], "today 3-m", "")

    returned_queries = [s["query"] for s in signals]
    assert "ai marketing" in returned_queries
    assert "missing keyword" not in returned_queries  # omitted → Tier 2


def test_fetch_trends_sync_omits_all_zero_series() -> None:
    """All-zero series = Google Trends has no data → omit, fall through."""
    import pandas as pd

    mock_df = pd.DataFrame({"flat keyword": [0, 0, 0, 0], "real keyword": [40, 50, 60, 70]})
    mock_pt = MagicMock()
    mock_pt.interest_over_time.return_value = mock_df

    with patch("pytrends.request.TrendReq", return_value=mock_pt):
        signals = _fetch_trends_sync(["flat keyword", "real keyword"], "today 3-m", "")

    returned_queries = [s["query"] for s in signals]
    assert "real keyword" in returned_queries
    assert "flat keyword" not in returned_queries


def test_fetch_trends_sync_empty_df_returns_empty_list() -> None:
    import pandas as pd

    mock_pt = MagicMock()
    mock_pt.interest_over_time.return_value = pd.DataFrame()

    with patch("pytrends.request.TrendReq", return_value=mock_pt):
        signals = _fetch_trends_sync(["ai marketing"], "today 3-m", "")

    assert signals == []


def test_fetch_trends_sync_includes_source_field() -> None:
    import pandas as pd

    mock_df = pd.DataFrame({"seo tools": [30, 40, 50, 70]})
    mock_pt = MagicMock()
    mock_pt.interest_over_time.return_value = mock_df

    with patch("pytrends.request.TrendReq", return_value=mock_pt):
        signals = _fetch_trends_sync(["seo tools"], "today 3-m", "")

    assert signals[0]["source"] == "google_trends"


# ── Agent happy path ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_writes_signals_for_keywords_in_params() -> None:
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["ai marketing", "seo tools"]})

    mock_signals = [
        {"query": "ai marketing", "momentum": 7.5, "source": "google_trends"},
        {"query": "seo tools", "momentum": 4.2, "source": "google_trends"},
    ]

    with patch("agents.seo.trend_collector._fetch_trends_sync", return_value=mock_signals):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["signals_written"] == 2
    assert result.data["keywords_checked"] == 2
    assert "sources" in result.data


@pytest.mark.asyncio
async def test_fetches_validated_keywords_from_db_when_none_in_params() -> None:
    db = _make_db(validated_keywords=["content marketing", "keyword research"])
    ctx = _make_ctx(db)

    mock_signals = [
        {"query": "content marketing", "momentum": 6.0, "source": "google_trends"},
        {"query": "keyword research", "momentum": 5.0, "source": "google_trends"},
    ]

    with patch("agents.seo.trend_collector._fetch_trends_sync", return_value=mock_signals):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["signals_written"] == 2
    assert result.data["keywords_checked"] == 2


@pytest.mark.asyncio
async def test_no_keywords_returns_success_with_zero() -> None:
    db = _make_db(validated_keywords=[])
    ctx = _make_ctx(db)
    result = await TrendCollectorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["signals_written"] == 0
    assert result.data["keywords_checked"] == 0


@pytest.mark.asyncio
async def test_tokens_used_is_zero() -> None:
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["ai marketing"]})

    with patch(
        "agents.seo.trend_collector._fetch_trends_sync",
        return_value=[{"query": "ai marketing", "momentum": 5.0, "source": "google_trends"}],
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


# ── Tier fallback tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tier2_wikipedia_used_when_pytrends_returns_no_data() -> None:
    """Keywords omitted by pytrends fall through to Wikipedia."""
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["niche topic"]})

    with (
        patch("agents.seo.trend_collector._fetch_trends_sync", return_value=[]),
        patch(
            "agents.seo.trend_collector.WikipediaTrends.get_momentum",
            new=AsyncMock(return_value={"momentum": 6.3, "source": "wikipedia"}),
        ),
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["signals_written"] == 1
    assert result.data["sources"].get("wikipedia", 0) == 1


@pytest.mark.asyncio
async def test_tier3_reddit_used_when_tier2_fails() -> None:
    """When Wikipedia returns None, Reddit is tried."""
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["niche topic"]})

    with (
        patch("agents.seo.trend_collector._fetch_trends_sync", return_value=[]),
        patch(
            "agents.seo.trend_collector.WikipediaTrends.get_momentum",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "agents.seo.trend_collector.RedditTrends.get_momentum",
            new=AsyncMock(return_value={"momentum": 7.1, "source": "reddit"}),
        ),
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.data["sources"].get("reddit", 0) == 1
    assert result.data["signals_written"] == 1


@pytest.mark.asyncio
async def test_tier4_google_suggest_used_when_tier2_and_tier3_fail() -> None:
    """When Wikipedia and Reddit both fail, Google Suggest is tried."""
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["niche topic"]})

    with (
        patch("agents.seo.trend_collector._fetch_trends_sync", return_value=[]),
        patch(
            "agents.seo.trend_collector.WikipediaTrends.get_momentum",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "agents.seo.trend_collector.RedditTrends.get_momentum",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "agents.seo.trend_collector._google_suggest_momentum",
            new=AsyncMock(return_value={"momentum": 4.6, "source": "google_suggest"}),
        ),
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.data["sources"].get("google_suggest", 0) == 1
    assert result.data["signals_written"] == 1


@pytest.mark.asyncio
async def test_tier5_neutral_fallback_when_all_tiers_fail() -> None:
    """When all tiers fail, neutral_fallback is used and agent still succeeds."""
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["ai marketing", "seo tools"]})

    with (
        patch("agents.seo.trend_collector._fetch_trends_sync", side_effect=Exception("rate limited")),
        patch(
            "agents.seo.trend_collector.WikipediaTrends.get_momentum",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "agents.seo.trend_collector.RedditTrends.get_momentum",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "agents.seo.trend_collector._google_suggest_momentum",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["signals_written"] == 2
    assert result.data["sources"].get("neutral_fallback", 0) == 2


@pytest.mark.asyncio
async def test_pytrends_failure_writes_neutral_momentum_fallback() -> None:
    """Legacy test: if pytrends raises and all other tiers fail, signals are still written."""
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["ai marketing", "seo tools"]})

    with (
        patch(
            "agents.seo.trend_collector._fetch_trends_sync",
            side_effect=Exception("Google Trends rate limit"),
        ),
        patch(
            "agents.seo.trend_collector.WikipediaTrends.get_momentum",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "agents.seo.trend_collector.RedditTrends.get_momentum",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "agents.seo.trend_collector._google_suggest_momentum",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["signals_written"] == 2


@pytest.mark.asyncio
async def test_mixed_tier_results_per_keyword() -> None:
    """Different keywords can land on different tiers in the same run."""
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["popular topic", "niche topic"]})

    # pytrends only has data for "popular topic"
    pytrends_signals = [{"query": "popular topic", "momentum": 8.0, "source": "google_trends"}]

    with (
        patch("agents.seo.trend_collector._fetch_trends_sync", return_value=pytrends_signals),
        patch(
            "agents.seo.trend_collector.WikipediaTrends.get_momentum",
            new=AsyncMock(return_value={"momentum": 5.5, "source": "wikipedia"}),
        ),
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.data["signals_written"] == 2
    sources = result.data["sources"]
    assert sources.get("google_trends", 0) == 1
    assert sources.get("wikipedia", 0) == 1


# ── Batching tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batches_five_keywords_per_pytrends_call() -> None:
    keywords = [f"keyword_{i}" for i in range(11)]
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": keywords})

    call_batches: list[list[str]] = []

    def _capture_batch(batch, timeframe, geo):
        call_batches.append(list(batch))
        return [{"query": kw, "momentum": 5.0, "source": "google_trends"} for kw in batch]

    with patch("agents.seo.trend_collector._fetch_trends_sync", side_effect=_capture_batch):
        await TrendCollectorAgent().run(ctx)

    assert len(call_batches) == 3
    assert len(call_batches[0]) == 5
    assert len(call_batches[1]) == 5
    assert len(call_batches[2]) == 1


# ── Integrity tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_momentum_clamped_to_ten_on_write() -> None:
    """TrendSignalOutput contract clamps values > 10 on INSERT."""
    db = _make_db()
    ctx = _make_ctx(db, params={"keywords": ["trending keyword"]})

    with patch(
        "agents.seo.trend_collector._fetch_trends_sync",
        return_value=[{"query": "trending keyword", "momentum": 999.0, "source": "google_trends"}],
    ):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["signals_written"] == 1
    insert_call = [
        c for c in db.execute.call_args_list
        if "INSERT INTO trend_signals" in str(c.args[0])
    ]
    assert len(insert_call) == 1
    assert insert_call[0].args[1]["momentum"] == 10.0


@pytest.mark.asyncio
async def test_golden_trace_matches_expected_shape() -> None:
    """Verify the agent produces the fields the golden trace expects."""
    db = _make_db()
    ctx = _make_ctx(db, params=_TRACE["input_params"])

    # Golden trace mock returns signals that already have source field
    mock_return = [
        {**s, "source": s.get("source", "google_trends")}
        for s in _TRACE["mock_pytrends_return"]
    ]

    with patch("agents.seo.trend_collector._fetch_trends_sync", return_value=mock_return):
        result = await TrendCollectorAgent().run(ctx)

    assert result.status == _TRACE["expected_result"]["status"]
    for field in _TRACE["expected_result"]["data_fields_present"]:
        assert field in result.data


# ── _google_suggest_momentum unit tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_suggest_momentum_scales_with_count() -> None:
    """More suggestions → higher momentum score."""
    import respx
    import httpx

    with respx.mock:
        # 10 suggestions
        respx.get(_SUGGEST_URL_PATTERN()).mock(
            return_value=httpx.Response(
                200,
                json=["ai marketing", ["ai marketing tool", "ai marketing software",
                      "ai marketing platform", "ai marketing agency", "ai marketing examples",
                      "ai marketing trends", "ai marketing automation", "ai marketing strategy",
                      "ai marketing companies", "ai marketing benefits"]],
            )
        )
        result_high = await _google_suggest_momentum("ai marketing")

    with respx.mock:
        # 0 suggestions
        respx.get(_SUGGEST_URL_PATTERN()).mock(
            return_value=httpx.Response(200, json=["obscure term", []])
        )
        result_low = await _google_suggest_momentum("obscure term")

    assert result_high is not None
    assert result_low is not None
    assert result_high["momentum"] > result_low["momentum"]
    assert result_high["source"] == "google_suggest"


@pytest.mark.asyncio
async def test_suggest_momentum_returns_none_on_network_error() -> None:
    import respx
    import httpx

    with respx.mock:
        respx.get(_SUGGEST_URL_PATTERN()).mock(side_effect=httpx.ConnectError("timeout"))
        result = await _google_suggest_momentum("some keyword")

    assert result is None


def _SUGGEST_URL_PATTERN():
    """Pattern matching suggestqueries.google.com."""
    import re
    return re.compile(r"https://suggestqueries\.google\.com/.*")
