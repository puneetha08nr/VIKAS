"""Unit tests for wordpress_publisher agent."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agent_base import AgentContext, AgentResult

ORG_ID = "00000000-0000-0000-0000-000000000001"
ARTICLE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

WP_POST_RESPONSE = {
    "id": 42,
    "link": "https://example.com/ai-marketing-guide/",
    "status": "draft",
}


def _ctx(db, params=None):
    llm = MagicMock()
    return AgentContext(
        org_id=ORG_ID,
        run_id="run-1",
        params={"article_id": ARTICLE_ID} if params is None else params,
        config={},
        db=db,
        llm=llm,
    )


def _mock_db(found=True):
    db = MagicMock()
    article_result = MagicMock()
    if found:
        row = MagicMock()
        row.__getitem__ = lambda self, i: [ARTICLE_ID, "AI Marketing Guide", "<p>Body</p>"][i]
        article_result.fetchone = MagicMock(return_value=row)
    else:
        article_result.fetchone = MagicMock(return_value=None)

    async def side_effect(query, params=None):
        sql = str(query)
        if "articles" in sql and "SELECT" in sql:
            return article_result
        return MagicMock()

    db.execute = AsyncMock(side_effect=side_effect)
    db.flush = AsyncMock()
    return db


def _mock_wp():
    wp = MagicMock()
    wp.create_post = AsyncMock(return_value=WP_POST_RESPONSE)
    return wp


@pytest.mark.asyncio
async def test_missing_article_id_fails():
    from agents.knowledge.wordpress_publisher import WordPressPublisherAgent
    db = _mock_db()
    result = await WordPressPublisherAgent().execute(_ctx(db, {}))
    assert result.status == "failed"
    assert "article_id" in result.error


@pytest.mark.asyncio
async def test_unknown_article_fails():
    from agents.knowledge.wordpress_publisher import WordPressPublisherAgent
    db = _mock_db(found=False)
    with patch("agents.knowledge.wordpress_publisher._build_integration", return_value=_mock_wp()):
        result = await WordPressPublisherAgent().execute(_ctx(db))
    assert result.status == "failed"
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_missing_wp_config_fails():
    from agents.knowledge.wordpress_publisher import WordPressPublisherAgent
    db = _mock_db()
    with patch("agents.knowledge.wordpress_publisher._build_integration", return_value=None):
        result = await WordPressPublisherAgent().execute(_ctx(db))
    assert result.status == "failed"
    assert "WordPress" in result.error


@pytest.mark.asyncio
async def test_success():
    from agents.knowledge.wordpress_publisher import WordPressPublisherAgent
    db = _mock_db()
    with patch("agents.knowledge.wordpress_publisher._build_integration", return_value=_mock_wp()):
        result = await WordPressPublisherAgent().execute(_ctx(db))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_output_has_wp_post_id():
    from agents.knowledge.wordpress_publisher import WordPressPublisherAgent
    db = _mock_db()
    with patch("agents.knowledge.wordpress_publisher._build_integration", return_value=_mock_wp()):
        result = await WordPressPublisherAgent().execute(_ctx(db))
    assert result.data["wp_post_id"] == 42


@pytest.mark.asyncio
async def test_output_has_published_url():
    from agents.knowledge.wordpress_publisher import WordPressPublisherAgent
    db = _mock_db()
    with patch("agents.knowledge.wordpress_publisher._build_integration", return_value=_mock_wp()):
        result = await WordPressPublisherAgent().execute(_ctx(db))
    assert result.data["published_url"] == "https://example.com/ai-marketing-guide/"


@pytest.mark.asyncio
async def test_db_update_called():
    from agents.knowledge.wordpress_publisher import WordPressPublisherAgent
    db = _mock_db()
    with patch("agents.knowledge.wordpress_publisher._build_integration", return_value=_mock_wp()):
        await WordPressPublisherAgent().execute(_ctx(db))
    calls = [str(c.args[0]) for c in db.execute.call_args_list if "UPDATE articles" in str(c.args[0])]
    assert len(calls) >= 1


@pytest.mark.asyncio
async def test_db_flush_called():
    from agents.knowledge.wordpress_publisher import WordPressPublisherAgent
    db = _mock_db()
    with patch("agents.knowledge.wordpress_publisher._build_integration", return_value=_mock_wp()):
        await WordPressPublisherAgent().execute(_ctx(db))
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_wp_api_error_fails():
    from agents.knowledge.wordpress_publisher import WordPressPublisherAgent
    db = _mock_db()
    bad_wp = MagicMock()
    bad_wp.create_post = AsyncMock(side_effect=Exception("Connection refused"))
    with patch("agents.knowledge.wordpress_publisher._build_integration", return_value=bad_wp):
        result = await WordPressPublisherAgent().execute(_ctx(db))
    assert result.status == "failed"
    assert "WordPress API error" in result.error


@pytest.mark.asyncio
async def test_invalid_wp_status_defaults_to_draft():
    from agents.knowledge.wordpress_publisher import WordPressPublisherAgent
    db = _mock_db()
    wp = _mock_wp()
    with patch("agents.knowledge.wordpress_publisher._build_integration", return_value=wp):
        result = await WordPressPublisherAgent().execute(_ctx(db, {"article_id": ARTICLE_ID, "wp_status": "live"}))
    assert result.status == "success"
    wp.create_post.assert_called_once()
    call_kwargs = wp.create_post.call_args.kwargs
    assert call_kwargs.get("status") == "draft"
