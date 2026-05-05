"""Unit tests for ArticlePlannerAgent."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import agents.content.article_planner  # noqa: F401

from agents.content.article_planner import ArticlePlannerAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"
OPP_ID = "aaaaaaaa-0000-0000-0000-000000000001"

_MOCK_PLAN = {
    "title": "Top AI Marketing Tools for 2025",
    "meta_description": "Discover the best AI marketing tools.",
    "word_count_target": 1800,
    "outline": [{"h2": "Introduction", "description": "overview", "h3s": []}],
    "content_angle": "practical guide",
    "cta": "Start free trial",
}
_MOCK_LLM = json.dumps(_MOCK_PLAN)
_MOCK_PROMPT = "You are a content strategist. Keyword: KEYWORD Brand: BRAND_VOICE Chunks: KNOWLEDGE_CHUNKS"


def _make_db(has_opportunity=True, has_bv=False, has_chunks=False) -> AsyncMock:
    db = AsyncMock()

    opp_result = MagicMock()
    opp_row = (OPP_ID, "ai marketing tools") if has_opportunity else None
    opp_result.fetchone.return_value = opp_row

    bv_result = MagicMock()
    bv_result.fetchone.return_value = ("professional", {}) if has_bv else None

    chunks_result = MagicMock()
    chunks_result.fetchall.return_value = [("chunk text",)] if has_chunks else []

    prompt_result = MagicMock()
    prompt_result.fetchone.return_value = (_MOCK_PROMPT,)

    write_result = MagicMock()

    call_count = [0]
    async def side_effect(query, params=None):
        sql = str(query)
        if "FROM opportunities" in sql:
            return opp_result
        if "FROM brand_voice" in sql:
            return bv_result
        if "FROM knowledge_chunks" in sql:
            return chunks_result
        if "FROM prompts" in sql:
            return prompt_result
        return write_result

    db.execute = AsyncMock(side_effect=side_effect)
    db.flush = AsyncMock()
    return db


def _ctx(db, params=None):
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=_MOCK_LLM)
    return AgentContext(
        org_id=ORG_ID, run_id=RUN_ID,
        params={"opportunity_id": OPP_ID} if params is None else params,
        config={}, db=db, llm=llm,
    )


class TestValidation:
    @pytest.mark.asyncio
    async def test_missing_opportunity_id_fails(self):
        db = _make_db()
        result = await ArticlePlannerAgent().run(_ctx(db, {}))
        assert result.status == "failed"
        assert "opportunity_id" in result.error

    @pytest.mark.asyncio
    async def test_unknown_opportunity_fails(self):
        db = _make_db(has_opportunity=False)
        result = await ArticlePlannerAgent().run(_ctx(db))
        assert result.status == "failed"


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_success_status(self):
        db = _make_db()
        result = await ArticlePlannerAgent().run(_ctx(db))
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_article_plan_id_is_uuid(self):
        import uuid
        db = _make_db()
        result = await ArticlePlannerAgent().run(_ctx(db))
        uuid.UUID(result.data["article_plan_id"])

    @pytest.mark.asyncio
    async def test_title_from_llm(self):
        db = _make_db()
        result = await ArticlePlannerAgent().run(_ctx(db))
        assert result.data["title"] == _MOCK_PLAN["title"]

    @pytest.mark.asyncio
    async def test_outline_sections_count(self):
        db = _make_db()
        result = await ArticlePlannerAgent().run(_ctx(db))
        assert result.data["outline_sections"] == 1

    @pytest.mark.asyncio
    async def test_insert_called(self):
        db = _make_db()
        await ArticlePlannerAgent().run(_ctx(db))
        inserts = [c for c in db.execute.call_args_list
                   if "INSERT INTO article_plans" in str(c[0][0])]
        assert len(inserts) == 1

    @pytest.mark.asyncio
    async def test_flush_called(self):
        db = _make_db()
        await ArticlePlannerAgent().run(_ctx(db))
        assert db.flush.call_count >= 1

    @pytest.mark.asyncio
    async def test_status_is_planned(self):
        db = _make_db()
        result = await ArticlePlannerAgent().run(_ctx(db))
        assert result.data["status"] == "planned"
