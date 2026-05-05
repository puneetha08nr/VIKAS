"""Unit tests for ArticleWriterAgent."""
from unittest.mock import AsyncMock, MagicMock

import pytest

import agents.content.article_writer  # noqa: F401

from agents.content.article_writer import ArticleWriterAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"
PLAN_ID = "bbbbbbbb-0000-0000-0000-000000000001"

_MOCK_OUTLINE = [
    {"h2": "Why AI Transforms Marketing", "description": "overview", "h3s": ["Benefits"]},
    {"h2": "Implementation Guide", "description": "how-to", "h3s": ["Step 1", "Step 2"]},
]
_MOCK_PROMPT = (
    "Write section: SECTION_TITLE for ARTICLE_TITLE targeting KEYWORD. "
    "Brand: BRAND_VOICE Outline: SECTION_OUTLINE Facts: KNOWLEDGE_CHUNKS "
    "Links: INTERNAL_LINKS Target: WORD_COUNT words."
)
_MOCK_SECTION_HTML = "<p>Great content about AI marketing tools.</p>"


def _make_db(has_plan=True) -> AsyncMock:
    db = AsyncMock()

    plan_result = MagicMock()
    plan_row = (PLAN_ID, "ai marketing", "AI Marketing Guide", _MOCK_OUTLINE, 1800) if has_plan else None
    plan_result.fetchone.return_value = plan_row

    bv_result = MagicMock()
    bv_result.fetchone.return_value = None

    chunks_result = MagicMock()
    chunks_result.fetchall.return_value = []

    prompt_result = MagicMock()
    prompt_result.fetchone.return_value = (_MOCK_PROMPT,)

    write_result = MagicMock()

    async def side_effect(query, params=None):
        sql = str(query)
        if "FROM article_plans" in sql and "SELECT" in sql:
            return plan_result
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
    llm.complete = AsyncMock(return_value=_MOCK_SECTION_HTML)
    return AgentContext(
        org_id=ORG_ID, run_id=RUN_ID,
        params={"article_plan_id": PLAN_ID} if params is None else params,
        config={}, db=db, llm=llm,
    )


class TestValidation:
    @pytest.mark.asyncio
    async def test_missing_plan_id_fails(self):
        db = _make_db()
        result = await ArticleWriterAgent().run(_ctx(db, {}))
        assert result.status == "failed"
        assert "article_plan_id" in result.error

    @pytest.mark.asyncio
    async def test_unknown_plan_fails(self):
        db = _make_db(has_plan=False)
        result = await ArticleWriterAgent().run(_ctx(db))
        assert result.status == "failed"


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_success_status(self):
        db = _make_db()
        result = await ArticleWriterAgent().run(_ctx(db))
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_article_id_is_uuid(self):
        import uuid
        db = _make_db()
        result = await ArticleWriterAgent().run(_ctx(db))
        uuid.UUID(result.data["article_id"])

    @pytest.mark.asyncio
    async def test_sections_written_equals_outline_h2s(self):
        db = _make_db()
        result = await ArticleWriterAgent().run(_ctx(db))
        assert result.data["sections_written"] == len(_MOCK_OUTLINE)

    @pytest.mark.asyncio
    async def test_article_insert_called(self):
        db = _make_db()
        await ArticleWriterAgent().run(_ctx(db))
        inserts = [c for c in db.execute.call_args_list
                   if "INSERT INTO articles" in str(c[0][0])]
        assert len(inserts) == 1

    @pytest.mark.asyncio
    async def test_plan_status_updated_to_written(self):
        db = _make_db()
        await ArticleWriterAgent().run(_ctx(db))
        updates = [c for c in db.execute.call_args_list
                   if "UPDATE article_plans" in str(c[0][0])]
        assert len(updates) == 1

    @pytest.mark.asyncio
    async def test_status_is_draft(self):
        db = _make_db()
        result = await ArticleWriterAgent().run(_ctx(db))
        assert result.data["status"] == "draft"

    @pytest.mark.asyncio
    async def test_word_count_positive(self):
        db = _make_db()
        result = await ArticleWriterAgent().run(_ctx(db))
        assert result.data["word_count"] > 0
