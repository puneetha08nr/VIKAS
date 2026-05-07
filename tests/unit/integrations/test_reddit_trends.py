"""Unit tests for RedditTrends — timestamp-based window scoring."""
import time

import httpx
import pytest
import respx

from integrations.reddit_trends import (
    RedditTrends,
    _compute_momentum,
    _split_by_window,
)

NOW = time.time()
DAY = 86400


# ── _split_by_window ──────────────────────────────────────────────────────────

def _post(age_days: float) -> dict:
    return {"created_utc": NOW - age_days * DAY}


def test_split_counts_recent_posts() -> None:
    posts = [_post(5), _post(10), _post(20)]  # all within 30 days
    recent, baseline = _split_by_window(posts)
    assert recent == 3
    assert baseline == 0


def test_split_counts_baseline_posts() -> None:
    posts = [_post(35), _post(45), _post(55)]  # all in 30-60 day window
    recent, baseline = _split_by_window(posts)
    assert recent == 0
    assert baseline == 3


def test_split_ignores_posts_older_than_60_days() -> None:
    posts = [_post(5), _post(65), _post(90)]
    recent, baseline = _split_by_window(posts)
    assert recent == 1
    assert baseline == 0


def test_split_boundary_at_30_days() -> None:
    # Exactly 30 days ago → baseline, not recent
    posts = [_post(29.9), _post(30.1)]
    recent, baseline = _split_by_window(posts)
    assert recent == 1
    assert baseline == 1


def test_split_mixed_distribution() -> None:
    posts = [
        _post(2), _post(7), _post(14),        # recent: 3
        _post(32), _post(45), _post(58),       # baseline: 3
        _post(70),                             # ignored
    ]
    recent, baseline = _split_by_window(posts)
    assert recent == 3
    assert baseline == 3


def test_split_empty_list_returns_zeros() -> None:
    recent, baseline = _split_by_window([])
    assert recent == 0
    assert baseline == 0


# ── _compute_momentum ─────────────────────────────────────────────────────────

def test_flat_distribution_returns_five() -> None:
    # recent == baseline → ratio 1.0 → momentum 5.0
    assert _compute_momentum(10, 10) == 5.0


def test_rising_trend_returns_above_five() -> None:
    # recent 20 vs baseline 10 → ratio 2.0 → 10.0
    assert _compute_momentum(20, 10) > 5.0


def test_falling_trend_returns_below_five() -> None:
    # recent 5 vs baseline 20 → ratio 0.25 → 1.25
    assert _compute_momentum(5, 20) < 5.0


def test_momentum_capped_at_ten() -> None:
    assert _compute_momentum(1000, 1) <= 10.0


def test_momentum_floored_at_zero() -> None:
    assert _compute_momentum(0, 1000) >= 0.0


def test_emerging_topic_scores_7_5() -> None:
    # baseline == 0, recent > 0 → new topic emerging
    assert _compute_momentum(5, 0) == 7.5


def test_no_posts_at_all_returns_five() -> None:
    assert _compute_momentum(0, 0) == 5.0


# ── Integration: score differentiation between keywords ───────────────────────

def test_niche_keyword_scores_lower_than_popular() -> None:
    """Trending popular keyword should beat niche keyword."""
    # popular: evenly distributed recent activity
    popular_recent, popular_baseline = 15, 10
    # niche: declining
    niche_recent, niche_baseline = 5, 15

    popular_score = _compute_momentum(popular_recent, popular_baseline)
    niche_score = _compute_momentum(niche_recent, niche_baseline)

    assert popular_score > niche_score


def test_below_minimum_posts_returns_none() -> None:
    """Fewer than _MIN_POSTS total posts → returns None (fall to Tier 4)."""
    # Only 2 posts in the window
    posts = [_post(5), _post(35)]

    reddit = RedditTrends()
    recent, baseline = _split_by_window(posts)
    assert recent + baseline == 2  # below _MIN_POSTS=3 → agent returns None


# ── HTTP mocking via respx ────────────────────────────────────────────────────

def _make_children(age_days_list: list[float]) -> list[dict]:
    return [{"data": _post(d)} for d in age_days_list]


@pytest.mark.asyncio
async def test_get_momentum_uses_exact_phrase_search() -> None:
    """Verify the API call quotes the keyword for phrase matching."""
    with respx.mock:
        route = respx.get("https://www.reddit.com/search.json").mock(
            return_value=httpx.Response(
                200,
                json={"data": {"children": _make_children([5, 10, 35, 45, 50])}},
            )
        )
        result = await RedditTrends().get_momentum("ai marketing")

    assert result is not None
    # Verify exact phrase quoting in the request
    assert route.called
    request_url = str(route.calls[0].request.url)
    assert "%22ai+marketing%22" in request_url or '"ai marketing"' in request_url


@pytest.mark.asyncio
async def test_get_momentum_rising_trend() -> None:
    """More recent posts than baseline → momentum above 5."""
    # 6 recent (0-30d), 2 baseline (30-60d) → ratio 3.0 → 10.0 (capped)
    posts = _make_children([2, 5, 8, 12, 18, 25, 35, 50])
    with respx.mock:
        respx.get("https://www.reddit.com/search.json").mock(
            return_value=httpx.Response(200, json={"data": {"children": posts}})
        )
        result = await RedditTrends().get_momentum("hot topic")

    assert result is not None
    assert result["momentum"] > 5.0
    assert result["source"] == "reddit"


@pytest.mark.asyncio
async def test_get_momentum_falling_trend() -> None:
    """Fewer recent posts than baseline → momentum below 5."""
    # 2 recent, 6 baseline → ratio 0.33 → 1.67
    posts = _make_children([5, 15, 35, 38, 42, 45, 50, 55])
    with respx.mock:
        respx.get("https://www.reddit.com/search.json").mock(
            return_value=httpx.Response(200, json={"data": {"children": posts}})
        )
        result = await RedditTrends().get_momentum("fading topic")

    assert result is not None
    assert result["momentum"] < 5.0


@pytest.mark.asyncio
async def test_get_momentum_returns_none_when_too_few_posts() -> None:
    """< _MIN_POSTS posts in 60-day window → return None (fall to Tier 4)."""
    # Only 2 posts
    posts = _make_children([5, 40])
    with respx.mock:
        respx.get("https://www.reddit.com/search.json").mock(
            return_value=httpx.Response(200, json={"data": {"children": posts}})
        )
        result = await RedditTrends().get_momentum("very niche keyword")

    assert result is None


@pytest.mark.asyncio
async def test_get_momentum_returns_none_on_429() -> None:
    with respx.mock:
        respx.get("https://www.reddit.com/search.json").mock(
            return_value=httpx.Response(429)
        )
        result = await RedditTrends().get_momentum("any keyword")

    assert result is None


@pytest.mark.asyncio
async def test_get_momentum_returns_none_on_network_error() -> None:
    with respx.mock:
        respx.get("https://www.reddit.com/search.json").mock(
            side_effect=httpx.ConnectError("timeout")
        )
        result = await RedditTrends().get_momentum("any keyword")

    assert result is None


@pytest.mark.asyncio
async def test_popular_vs_niche_real_differentiation() -> None:
    """Simulate: popular keyword has steady activity, niche keyword is fading.

    popular: 8 recent / 8 baseline → ratio 1.0 → momentum 5.0
    niche:   2 recent / 6 baseline → ratio 0.33 → momentum 1.67

    Popular should outscore niche.
    """
    popular_posts = _make_children([3, 6, 9, 12, 18, 22, 26, 29,   # recent: 8
                                    32, 36, 40, 44, 48, 52, 56, 58])  # baseline: 8
    niche_posts = _make_children([10, 25,           # recent: 2
                                  35, 42, 50, 57])  # baseline: 4

    with respx.mock:
        respx.get("https://www.reddit.com/search.json").mock(
            side_effect=[
                httpx.Response(200, json={"data": {"children": popular_posts}}),
                httpx.Response(200, json={"data": {"children": niche_posts}}),
            ]
        )
        popular_result = await RedditTrends().get_momentum("project management software")
        niche_result = await RedditTrends().get_momentum("blockchain marketing")

    assert popular_result is not None
    assert niche_result is not None
    assert popular_result["momentum"] > niche_result["momentum"]
