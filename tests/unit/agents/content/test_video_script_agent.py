"""Unit tests for VideoScriptAgent."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.content.video_script_agent  # noqa: F401
from agents.content.video_script_agent import VideoScriptAgent, _parse_script
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"
ITEM_ID = "aa000001-0000-0000-0000-000000000001"
OPP_ID  = "dddddddd-0000-0000-0000-000000000001"

_VALID_SCRIPT = {
    "title": "How AI Tools Save Marketers 10 Hours a Week",
    "total_duration_seconds": 200,
    "scenes": [
        {"scene_number": 1, "title": "Hook", "narration": "You are wasting 10 hours a week.", "visual": "Text overlay", "b_roll": "Time-lapse", "duration_seconds": 15},
        {"scene_number": 2, "title": "Problem", "narration": "Most teams do repetitive tasks.", "visual": "Screen recording", "b_roll": "Office footage", "duration_seconds": 30},
    ],
    "cta": "Try AI marketing tools free at vikas.ai",
}
_LLM_RESPONSE = json.dumps(_VALID_SCRIPT)


def _make_db(item_found: bool = True, article_body: str = "<p>article</p>") -> AsyncMock:
    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM content_items ci" in sql and "JOIN opportunities" in sql:
            result.fetchone.return_value = (ITEM_ID, "video_script", "Video Script: Ai Marketing Tools", OPP_ID, "ai marketing tools") if item_found else None
        elif "FROM content_items" in sql and "'article'" in sql:
            result.fetchone.return_value = (article_body,) if article_body else None
        else:
            result.fetchone.return_value = None
        return result
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _make_ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    llm = MagicMock()
    llm.last_tokens_used = 600
    llm.last_cost_usd = 0.009
    return AgentContext(org_id=ORG_ID, run_id=RUN_ID, params={"content_item_id": ITEM_ID, **(params or {})}, config={}, db=db, llm=llm)


def test_parse_clean_json() -> None:
    result = _parse_script(json.dumps(_VALID_SCRIPT))
    assert result is not None
    assert len(result["scenes"]) == 2


def test_parse_fenced_json() -> None:
    assert _parse_script(f"```json\n{json.dumps(_VALID_SCRIPT)}\n```") is not None


def test_parse_empty_returns_none() -> None:
    assert _parse_script("") is None


@pytest.mark.asyncio
async def test_missing_id_returns_failed() -> None:
    db = _make_db()
    ctx = AgentContext(org_id=ORG_ID, run_id=RUN_ID, params={}, config={}, db=db, llm=MagicMock())
    result = await VideoScriptAgent().run(ctx)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_wrong_format_returns_failed() -> None:
    def _side(query, params=None):
        result = MagicMock()
        if "FROM content_items ci" in str(query):
            result.fetchone.return_value = (ITEM_ID, "article", "Guide", OPP_ID, "ai tools")
        else:
            result.fetchone.return_value = None
        return result
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    ctx = _make_ctx(db)
    with patch("agents.content.video_script_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="SOURCE_CONTENT PRIMARY_KEYWORD TARGET_DURATION")
        result = await VideoScriptAgent().run(ctx)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_happy_path_with_article() -> None:
    db = _make_db()
    ctx = _make_ctx(db)
    with patch("agents.content.video_script_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="SOURCE_CONTENT PRIMARY_KEYWORD TARGET_DURATION")
        ctx.llm.complete = AsyncMock(return_value=_LLM_RESPONSE)
        result = await VideoScriptAgent().run(ctx)
    assert result.status == "success"
    assert result.data["scene_count"] == 2
    assert result.data["source"] == "article"


@pytest.mark.asyncio
async def test_happy_path_keyword_only() -> None:
    db = _make_db(article_body="")
    ctx = _make_ctx(db)
    with patch("agents.content.video_script_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="SOURCE_CONTENT PRIMARY_KEYWORD TARGET_DURATION")
        ctx.llm.complete = AsyncMock(return_value=_LLM_RESPONSE)
        result = await VideoScriptAgent().run(ctx)
    assert result.status == "success"
    assert result.data["source"] == "keyword_only"


@pytest.mark.asyncio
async def test_bad_llm_response_returns_failed() -> None:
    db = _make_db()
    ctx = _make_ctx(db)
    with patch("agents.content.video_script_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="SOURCE_CONTENT PRIMARY_KEYWORD TARGET_DURATION")
        ctx.llm.complete = AsyncMock(return_value="I cannot write that.")
        result = await VideoScriptAgent().run(ctx)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_tokens_and_flush() -> None:
    db = _make_db()
    ctx = _make_ctx(db)
    with patch("agents.content.video_script_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="SOURCE_CONTENT PRIMARY_KEYWORD TARGET_DURATION")
        ctx.llm.complete = AsyncMock(return_value=_LLM_RESPONSE)
        result = await VideoScriptAgent().run(ctx)
    assert result.tokens_used == 600
    assert db.flush.called
