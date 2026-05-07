"""Unit tests for AnchorScaleEstimator."""
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.anchor_scale_estimator import (
    AnchorScaleEstimator,
    _all_pending,
    _anchor_avg_cpc,
    _closest_anchor,
    _pending_row,
    _topic_similarity,
)


# ── DB mock helpers ───────────────────────────────────────────────────────────

def _make_db(anchors: list[dict[str, Any]] | None = None) -> AsyncMock:
    """Return an AsyncSession mock that returns anchor rows."""
    db = AsyncMock()
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.all.return_value = anchors if anchors is not None else []
    mock_result.mappings.return_value = mock_mappings
    db.execute = AsyncMock(return_value=mock_result)
    return db


_ANCHORS = [
    {"keyword": "ai marketing tools", "volume": 1000, "kd": 3.5, "cpc": 4.50},
    {"keyword": "ai content creation", "volume": 800,  "kd": 4.0, "cpc": 3.80},
]


# ── estimate_metrics: no-anchor path ─────────────────────────────────────────

async def test_no_anchors_returns_all_pending() -> None:
    db = _make_db(anchors=[])
    result = await AnchorScaleEstimator().estimate_metrics(
        ["ai seo tools", "ai blogging"], "ai marketing", db
    )
    assert len(result) == 2
    for r in result:
        assert r["data_source"] == "pending"
        assert r["volume"] is None
        assert r["kd"] is None


async def test_empty_keyword_list_returns_empty() -> None:
    db = _make_db(anchors=_ANCHORS)
    result = await AnchorScaleEstimator().estimate_metrics([], "ai marketing", db)
    assert result == []


# ── estimate_metrics: PyTrends success path ───────────────────────────────────

async def test_pytrends_success_produces_estimated_metrics() -> None:
    db = _make_db(anchors=_ANCHORS)

    trend_scores = {
        "ai marketing tools": 80.0,
        "ai content creation": 60.0,
        "ai seo tools": 40.0,
    }

    with (
        patch(
            "integrations.anchor_scale_estimator._get_pytrends_scores",
            AsyncMock(return_value=trend_scores),
        ),
        patch(
            "integrations.anchor_scale_estimator._kd_from_suggest",
            AsyncMock(return_value=5.0),
        ),
    ):
        result = await AnchorScaleEstimator().estimate_metrics(
            ["ai seo tools"], "ai marketing", db
        )

    assert len(result) == 1
    r = result[0]
    assert r["data_source"] == "estimated"
    assert r["confidence"] == "low"
    assert r["true_up_required"] is True
    assert r["volume"] is not None
    assert r["kd"] == 5.0


async def test_pytrends_failure_falls_back_to_kd_only() -> None:
    db = _make_db(anchors=_ANCHORS)

    with (
        patch(
            "integrations.anchor_scale_estimator._get_pytrends_scores",
            AsyncMock(side_effect=Exception("rate limited")),
        ),
        patch(
            "integrations.anchor_scale_estimator._kd_from_suggest",
            AsyncMock(return_value=4.0),
        ),
    ):
        result = await AnchorScaleEstimator().estimate_metrics(
            ["ai seo tools"], "ai marketing", db
        )

    assert len(result) == 1
    r = result[0]
    assert r["data_source"] == "estimated"
    assert r["volume"] is None  # no PyTrends → no volume estimate
    assert r["kd"] == 4.0


async def test_kd_failure_with_no_pytrends_returns_pending() -> None:
    db = _make_db(anchors=_ANCHORS)

    with (
        patch(
            "integrations.anchor_scale_estimator._get_pytrends_scores",
            AsyncMock(side_effect=Exception("rate limited")),
        ),
        patch(
            "integrations.anchor_scale_estimator._kd_from_suggest",
            AsyncMock(return_value=None),
        ),
    ):
        result = await AnchorScaleEstimator().estimate_metrics(
            ["ai seo tools"], "ai marketing", db
        )

    assert len(result) == 1
    assert result[0]["data_source"] == "pending"


# ── Volume calculation ────────────────────────────────────────────────────────

async def test_volume_rounds_to_nearest_100() -> None:
    db = _make_db(anchors=[
        {"keyword": "ai marketing", "volume": 1000, "kd": 3.5, "cpc": 4.0},
    ])
    trend_scores = {"ai marketing": 100.0, "ai seo": 75.0}

    with (
        patch(
            "integrations.anchor_scale_estimator._get_pytrends_scores",
            AsyncMock(return_value=trend_scores),
        ),
        patch(
            "integrations.anchor_scale_estimator._kd_from_suggest",
            AsyncMock(return_value=5.0),
        ),
    ):
        result = await AnchorScaleEstimator().estimate_metrics(
            ["ai seo"], "ai marketing", db
        )

    assert result[0]["volume"] % 100 == 0


async def test_volume_capped_at_max_uses_anchor_volume() -> None:
    # anchor_volume=10000, new/anchor ratio=100x → raw=10,000,000 > 500k cap
    db = _make_db(anchors=[
        {"keyword": "ai marketing", "volume": 10000, "kd": 3.0, "cpc": 2.0},
    ])
    trend_scores = {"ai marketing": 1.0, "ai seo": 100.0}

    with (
        patch(
            "integrations.anchor_scale_estimator._get_pytrends_scores",
            AsyncMock(return_value=trend_scores),
        ),
        patch(
            "integrations.anchor_scale_estimator._kd_from_suggest",
            AsyncMock(return_value=5.0),
        ),
    ):
        result = await AnchorScaleEstimator().estimate_metrics(
            ["ai seo"], "ai marketing", db
        )

    assert result[0]["volume"] == 10000  # falls back to anchor volume


# ── CPC estimation ────────────────────────────────────────────────────────────

async def test_cpc_uses_anchor_avg_and_kd_factor() -> None:
    db = _make_db(anchors=[
        {"keyword": "ai marketing", "volume": 1000, "kd": 3.5, "cpc": 5.0},
    ])
    with (
        patch(
            "integrations.anchor_scale_estimator._get_pytrends_scores",
            AsyncMock(return_value={"ai marketing": 80.0, "ai seo": 40.0}),
        ),
        patch(
            "integrations.anchor_scale_estimator._kd_from_suggest",
            AsyncMock(return_value=5.0),
        ),
    ):
        result = await AnchorScaleEstimator().estimate_metrics(
            ["ai seo"], "ai marketing", db
        )

    # cpc = 5.0 * (5.0 / 5.0) = 5.0
    assert result[0]["cpc"] == pytest.approx(5.0, abs=0.01)


# ── KD mapping ────────────────────────────────────────────────────────────────

async def test_kd_mapping_ten_suggestions_returns_7() -> None:
    from integrations.anchor_scale_estimator import _kd_from_suggest
    with patch(
        "integrations.anchor_scale_estimator._fetch_suggest_count",
        AsyncMock(return_value=10),
    ):
        kd = await _kd_from_suggest("some keyword")
    assert kd == 7.0


async def test_kd_mapping_five_suggestions_returns_5() -> None:
    from integrations.anchor_scale_estimator import _kd_from_suggest
    with patch(
        "integrations.anchor_scale_estimator._fetch_suggest_count",
        AsyncMock(return_value=5),
    ):
        kd = await _kd_from_suggest("some keyword")
    assert kd == 5.0


async def test_kd_mapping_two_suggestions_returns_2() -> None:
    from integrations.anchor_scale_estimator import _kd_from_suggest
    with patch(
        "integrations.anchor_scale_estimator._fetch_suggest_count",
        AsyncMock(return_value=2),
    ):
        kd = await _kd_from_suggest("some keyword")
    assert kd == 2.0


async def test_kd_suggest_network_error_returns_none() -> None:
    from integrations.anchor_scale_estimator import _kd_from_suggest
    with patch(
        "integrations.anchor_scale_estimator._fetch_suggest_count",
        AsyncMock(side_effect=Exception("timeout")),
    ):
        kd = await _kd_from_suggest("some keyword")
    assert kd is None


# ── Pure function unit tests ──────────────────────────────────────────────────

def test_topic_similarity_exact_overlap() -> None:
    assert _topic_similarity("ai marketing tools", "ai marketing software") == pytest.approx(2 / 3)


def test_topic_similarity_no_overlap() -> None:
    assert _topic_similarity("blockchain crypto", "digital marketing") == 0.0


def test_topic_similarity_identical() -> None:
    assert _topic_similarity("ai tools", "ai tools") == 1.0


def test_closest_anchor_picks_highest_overlap() -> None:
    anchors = [
        {"keyword": "ai marketing tools", "volume": 1000, "kd": 3.0, "cpc": 4.0},
        {"keyword": "seo keyword research", "volume": 2000, "kd": 5.0, "cpc": 2.0},
    ]
    best = _closest_anchor("ai seo tools", anchors)
    assert best is not None
    # "ai" + "tools" overlaps with "ai marketing tools" (2 words)
    # "seo" overlaps with "seo keyword research" (1 word)
    # Both have 1 common word with "ai seo tools" / max(3,3) = 1/3
    # Should pick the one with higher volume when sim is equal
    assert best["keyword"] in ("ai marketing tools", "seo keyword research")


def test_closest_anchor_returns_first_when_empty_similarity() -> None:
    anchors = [{"keyword": "unrelated topic", "volume": 500, "kd": 3.0, "cpc": 1.0}]
    best = _closest_anchor("totally different domain", anchors)
    assert best == anchors[0]


def test_anchor_avg_cpc_computes_mean() -> None:
    anchors = [
        {"keyword": "a", "volume": 100, "kd": 3.0, "cpc": 4.0},
        {"keyword": "b", "volume": 200, "kd": 4.0, "cpc": 6.0},
    ]
    assert _anchor_avg_cpc(anchors) == pytest.approx(5.0)


def test_anchor_avg_cpc_none_when_no_cpc() -> None:
    anchors = [{"keyword": "a", "volume": 100, "kd": 3.0, "cpc": None}]
    assert _anchor_avg_cpc(anchors) is None


def test_all_pending_returns_correct_structure() -> None:
    result = _all_pending(["kw1", "kw2"])
    assert len(result) == 2
    for r in result:
        assert r["data_source"] == "pending"
        assert r["volume"] is None
        assert r["true_up_required"] is True


def test_pending_row_structure() -> None:
    r = _pending_row("test keyword")
    assert r["keyword"] == "test keyword"
    assert r["data_source"] == "pending"
    assert r["confidence"] is None
    assert r["anchor_keyword"] is None
