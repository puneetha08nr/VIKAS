"""Unit tests for twitter_agent."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.agent_base import AgentContext, AgentResult

ORG_ID = "00000000-0000-0000-0000-000000000001"
ARTICLE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

LLM_RESPONSE = '[{"text": "Tweet 1 about AI"}, {"text": "Tweet 2 about AI"}, {"text": "Tweet 3 about AI"}]'


def _ctx(db, params=None):
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=LLM_RESPONSE)
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
        row.__getitem__ = lambda self, i: [ARTICLE_ID, "ai marketing", "AI Marketing Guide", "<p>Body</p>"][i]
        article_result.fetchone = MagicMock(return_value=row)
    else:
        article_result.fetchone = MagicMock(return_value=None)

    prompt_result = MagicMock()
    prompt_row = MagicMock()
    prompt_row.__getitem__ = lambda self, i: ["Write Twitter thread for ARTICLE_TITLE KEYWORD ARTICLE_BODY"][i]
    prompt_result.fetchone = MagicMock(return_value=prompt_row)

    async def side_effect(query, params=None):
        sql = str(query)
        if "articles" in sql:
            return article_result
        if "prompts" in sql:
            return prompt_result
        return MagicMock()

    db.execute = AsyncMock(side_effect=side_effect)
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_missing_article_id_fails():
    from agents.content.twitter_agent import TwitterAgent
    db = _mock_db()
    result = await TwitterAgent().execute(_ctx(db, {}))
    assert result.status == "failed"
    assert "article_id" in result.error


@pytest.mark.asyncio
async def test_unknown_article_fails():
    from agents.content.twitter_agent import TwitterAgent
    db = _mock_db(found=False)
    result = await TwitterAgent().execute(_ctx(db))
    assert result.status == "failed"
    assert "not found" in result.error


@pytest.mark.asyncio
async def test_success():
    from agents.content.twitter_agent import TwitterAgent
    db = _mock_db()
    result = await TwitterAgent().execute(_ctx(db))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_output_has_uuid():
    from agents.content.twitter_agent import TwitterAgent
    import uuid
    db = _mock_db()
    result = await TwitterAgent().execute(_ctx(db))
    uuid.UUID(result.data["twitter_thread_id"])


@pytest.mark.asyncio
async def test_tweet_count_in_output():
    from agents.content.twitter_agent import TwitterAgent
    db = _mock_db()
    result = await TwitterAgent().execute(_ctx(db))
    assert result.data["tweet_count"] == 3


@pytest.mark.asyncio
async def test_db_insert_called():
    from agents.content.twitter_agent import TwitterAgent
    db = _mock_db()
    await TwitterAgent().execute(_ctx(db))
    calls = [str(c.args[0]) for c in db.execute.call_args_list if "twitter_threads" in str(c.args[0])]
    assert len(calls) >= 1


@pytest.mark.asyncio
async def test_db_flush_called():
    from agents.content.twitter_agent import TwitterAgent
    db = _mock_db()
    await TwitterAgent().execute(_ctx(db))
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_fallback_on_plain_text():
    from agents.content.twitter_agent import TwitterAgent
    db = _mock_db()
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="Line one\nLine two\nLine three")
    ctx = AgentContext(org_id=ORG_ID, run_id="run-1", params={"article_id": ARTICLE_ID}, config={}, db=db, llm=llm)
    result = await TwitterAgent().execute(ctx)
    assert result.status == "success"
    assert result.data["tweet_count"] == 3


@pytest.mark.asyncio
async def test_status_draft():
    from agents.content.twitter_agent import TwitterAgent
    db = _mock_db()
    result = await TwitterAgent().execute(_ctx(db))
    assert result.data["status"] == "draft"
