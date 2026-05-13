"""Unit tests for SentimentAggregatorAgent and aggregation helpers."""
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

import agents.sentiment.aggregator  # noqa: F401

from agents.sentiment.aggregator import (
    SentimentAggregatorAgent,
    _compute_aggregates,
    _resolve_date,
)
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"


def _make_ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID, run_id=RUN_ID,
        params=params or {},
        config={}, db=db, llm=MagicMock(),
    )


def _row(polarity: str, score: float, weight: float = 1.0, themes: list | None = None) -> dict:
    return {
        "polarity": polarity,
        "polarity_score": score,
        "source_weight": weight,
        "themes": themes or [],
    }


def _make_db(
    pairs: list[tuple[str, str]] | None = None,
    analyzed_rows: list | None = None,
    baseline_neg_rate: float | None = None,
) -> AsyncMock:
    _pairs = pairs or [("amma_scheme", "madurai")]
    _rows = analyzed_rows or []

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "DISTINCT" in sql:
            result.fetchall.return_value = [MagicMock(__getitem__=lambda s, i: _pairs[0][i]
                                                      if i < 2 else None) for _ in _pairs[:1]]
            # Use tuple-based rows for pairs
            result.fetchall.return_value = [(_p[0], _p[1]) for _p in _pairs]
        elif "FROM analyzed_mentions" in sql and "JOIN" in sql and "polarity" in sql:
            rows = []
            for r in _rows:
                row = MagicMock()
                row._mapping = r
                rows.append(row)
            result.fetchall.return_value = rows
        elif "AVG" in sql and "negative_count" in sql:
            result.fetchone.return_value = (baseline_neg_rate,)
        elif "INSERT INTO sentiment_signals" in sql or "INSERT INTO scheme_patterns" in sql \
                or "INSERT INTO district_patterns" in sql:
            result.rowcount = 1
            result.fetchall.return_value = []
        elif "AVG(mention_count)" in sql:
            result.fetchall.return_value = []
        else:
            result.fetchall.return_value = []
            result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    return db


# ── Aggregate computation unit tests ─────────────────────────────────────────

def test_compute_aggregates_counts_polarities() -> None:
    rows = [
        _row("positive", 0.7),
        _row("negative", -0.8),
        _row("negative", -0.6),
        _row("neutral", 0.0),
    ]
    agg = _compute_aggregates(rows)
    assert agg["mention_count"] == 4
    assert agg["positive_count"] == 1
    assert agg["negative_count"] == 2
    assert agg["neutral_count"] == 1
    assert agg["mixed_count"] == 0


def test_compute_aggregates_dominant_polarity() -> None:
    rows = [_row("negative", -0.5)] * 3 + [_row("positive", 0.5)]
    agg = _compute_aggregates(rows)
    assert agg["dominant_polarity"] == "negative"


def test_compute_aggregates_avg_polarity_score() -> None:
    rows = [_row("positive", 0.8), _row("negative", -0.4)]
    agg = _compute_aggregates(rows)
    assert agg["avg_polarity_score"] == pytest.approx(0.2, abs=1e-4)


def test_compute_aggregates_weighted_avg() -> None:
    rows = [
        _row("positive", 1.0, weight=2.0),
        _row("negative", -1.0, weight=1.0),
    ]
    agg = _compute_aggregates(rows)
    # (1.0*2 + -1.0*1) / (2+1) = 1/3
    assert agg["weighted_avg_polarity_score"] == pytest.approx(1 / 3, abs=1e-3)


def test_compute_aggregates_dominant_themes_top_5() -> None:
    rows = [
        _row("neutral", 0.0, themes=["water_supply", "pension_delay"]),
        _row("neutral", 0.0, themes=["water_supply", "road_repair"]),
        _row("neutral", 0.0, themes=["water_supply"]),
    ]
    agg = _compute_aggregates(rows)
    assert agg["dominant_themes"][0] == "water_supply"
    assert len(agg["dominant_themes"]) <= 5


def test_compute_aggregates_empty_rows_no_crash() -> None:
    agg = _compute_aggregates([])
    assert agg["mention_count"] == 0
    assert agg["avg_polarity_score"] is None


# ── Date resolution tests ─────────────────────────────────────────────────────

def test_resolve_date_parses_iso_string() -> None:
    d = _resolve_date("2026-04-15")
    assert d == date(2026, 4, 15)


def test_resolve_date_empty_returns_yesterday() -> None:
    d = _resolve_date("")
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
    assert d == yesterday


def test_resolve_date_invalid_returns_yesterday() -> None:
    d = _resolve_date("not-a-date")
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date()
    assert d == yesterday


# ── Agent: no analyzed mentions → success with zero pairs ────────────────────

@pytest.mark.asyncio
async def test_no_pairs_returns_success() -> None:
    db = _make_db(pairs=[])
    ctx = _make_ctx(db, params={"signal_date": "2026-04-15"})
    result = await SentimentAggregatorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["pairs_aggregated"] == 0


# ── Agent: spike detected when negative rate exceeds baseline ─────────────────

@pytest.mark.asyncio
async def test_spike_detected_when_neg_rate_exceeds_2x_baseline() -> None:
    # 4 negative out of 5 = 80% negative rate
    rows = [_row("negative", -0.7)] * 4 + [_row("neutral", 0.0)]
    # Baseline: 20% negative rate → 80% > 2 * 20% → spike
    db = _make_db(
        pairs=[("amma_scheme", "madurai")],
        analyzed_rows=rows,
        baseline_neg_rate=0.20,
    )
    ctx = _make_ctx(db, params={"signal_date": "2026-04-15"})
    result = await SentimentAggregatorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["spikes_flagged"] == 1


@pytest.mark.asyncio
async def test_no_spike_when_neg_rate_within_baseline() -> None:
    rows = [_row("negative", -0.5)] * 2 + [_row("positive", 0.5)] * 8
    # 20% negative rate; baseline also 20% → no spike
    db = _make_db(
        pairs=[("amma_scheme", "madurai")],
        analyzed_rows=rows,
        baseline_neg_rate=0.20,
    )
    ctx = _make_ctx(db, params={"signal_date": "2026-04-15"})
    result = await SentimentAggregatorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["spikes_flagged"] == 0


@pytest.mark.asyncio
async def test_no_spike_when_below_minimum_mention_count() -> None:
    # Only 4 mentions — below _SPIKE_MIN_MENTIONS=5, no spike regardless of rate
    rows = [_row("negative", -0.9)] * 4
    db = _make_db(
        pairs=[("amma_scheme", "madurai")],
        analyzed_rows=rows,
        baseline_neg_rate=0.10,
    )
    ctx = _make_ctx(db, params={"signal_date": "2026-04-15"})
    result = await SentimentAggregatorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["spikes_flagged"] == 0
