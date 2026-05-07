"""Unit tests for ImageCreatorAgent — DALL-E call fully mocked."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.content.image_creator_agent  # noqa: F401
from agents.content.image_creator_agent import ImageCreatorAgent, _parse_image_prompt
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"
ITEM_ID = "cc000003-0000-0000-0000-000000000003"
OPP_ID  = "dddddddd-0000-0000-0000-000000000001"

_VALID_PROMPT = {
    "prompt": "A focused marketing professional at a clean desk with laptop, soft lighting, blue and white, photorealistic",
    "negative_prompt": "clutter, watermarks, distorted faces",
    "style": "photorealistic",
    "aspect_ratio": "16:9",
    "alt_text": "Marketing professional reviewing analytics dashboard",
}
_LLM_RESPONSE = json.dumps(_VALID_PROMPT)
_DALLE_URL = "https://oaidalleapiprodscus.blob.core.windows.net/test/image.png"


def _make_db(item_found: bool = True) -> AsyncMock:
    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM content_items ci" in sql and "JOIN opportunities" in sql:
            result.fetchone.return_value = (ITEM_ID, "article", "10 Best AI Marketing Tools", OPP_ID, "ai marketing tools") if item_found else None
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
    llm.last_tokens_used = 250
    llm.last_cost_usd = 0.00375
    return AgentContext(org_id=ORG_ID, run_id=RUN_ID, params={"content_item_id": ITEM_ID, **(params or {})}, config={}, db=db, llm=llm)


def test_parse_clean_json() -> None:
    result = _parse_image_prompt(json.dumps(_VALID_PROMPT))
    assert result is not None
    assert "prompt" in result


def test_parse_fenced_json() -> None:
    assert _parse_image_prompt(f"```json\n{json.dumps(_VALID_PROMPT)}\n```") is not None


def test_parse_empty_returns_none() -> None:
    assert _parse_image_prompt("") is None


@pytest.mark.asyncio
async def test_missing_id_returns_failed() -> None:
    db = _make_db()
    ctx = AgentContext(org_id=ORG_ID, run_id=RUN_ID, params={}, config={}, db=db, llm=MagicMock())
    result = await ImageCreatorAgent().run(ctx)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_wrong_format_returns_failed() -> None:
    def _side(query, params=None):
        result = MagicMock()
        if "FROM content_items ci" in str(query):
            result.fetchone.return_value = (ITEM_ID, "linkedin", "Post", OPP_ID, "ai tools")
        else:
            result.fetchone.return_value = None
        return result
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    ctx = _make_ctx(db)
    with patch("agents.content.image_creator_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="ARTICLE_TITLE PRIMARY_KEYWORD IMAGE_USE_CASE")
        result = await ImageCreatorAgent().run(ctx)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_happy_path_no_dalle_key() -> None:
    """Without DALL-E key, saves prompt only — image_generated=False."""
    db = _make_db()
    ctx = _make_ctx(db)
    with patch("agents.content.image_creator_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="ARTICLE_TITLE PRIMARY_KEYWORD IMAGE_USE_CASE")
        ctx.llm.complete = AsyncMock(return_value=_LLM_RESPONSE)
        with patch("agents.content.image_creator_agent._generate_image_dalle", side_effect=Exception("No API key")):
            result = await ImageCreatorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["image_generated"] is False
    assert result.data["image_url"] == ""


@pytest.mark.asyncio
async def test_happy_path_with_dalle() -> None:
    """With DALL-E key available, image_url is returned."""
    db = _make_db()
    ctx = _make_ctx(db)
    with patch("agents.content.image_creator_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="ARTICLE_TITLE PRIMARY_KEYWORD IMAGE_USE_CASE")
        ctx.llm.complete = AsyncMock(return_value=_LLM_RESPONSE)
        with patch("agents.content.image_creator_agent._generate_image_dalle", return_value=_DALLE_URL):
            result = await ImageCreatorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["image_generated"] is True
    assert result.data["image_url"] == _DALLE_URL


@pytest.mark.asyncio
async def test_invalid_style_defaults_to_photorealistic() -> None:
    bad = {**_VALID_PROMPT, "style": "watercolor_sketch"}
    db = _make_db()
    ctx = _make_ctx(db)
    with patch("agents.content.image_creator_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="ARTICLE_TITLE PRIMARY_KEYWORD IMAGE_USE_CASE")
        ctx.llm.complete = AsyncMock(return_value=json.dumps(bad))
        with patch("agents.content.image_creator_agent._generate_image_dalle", side_effect=Exception("no key")):
            result = await ImageCreatorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["style"] == "photorealistic"


@pytest.mark.asyncio
async def test_bad_llm_response_returns_failed() -> None:
    db = _make_db()
    ctx = _make_ctx(db)
    with patch("agents.content.image_creator_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="ARTICLE_TITLE PRIMARY_KEYWORD IMAGE_USE_CASE")
        ctx.llm.complete = AsyncMock(return_value="I cannot generate that.")
        result = await ImageCreatorAgent().run(ctx)
    assert result.status == "failed"


@pytest.mark.asyncio
async def test_tokens_and_flush() -> None:
    db = _make_db()
    ctx = _make_ctx(db)
    with patch("agents.content.image_creator_agent.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="ARTICLE_TITLE PRIMARY_KEYWORD IMAGE_USE_CASE")
        ctx.llm.complete = AsyncMock(return_value=_LLM_RESPONSE)
        with patch("agents.content.image_creator_agent._generate_image_dalle", side_effect=Exception("no key")):
            result = await ImageCreatorAgent().run(ctx)
    assert result.tokens_used == 250
    assert db.flush.called
