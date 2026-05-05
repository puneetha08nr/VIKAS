"""Unit tests for ai_assistant agent."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.agent_base import AgentContext, AgentResult

ORG_ID = "00000000-0000-0000-0000-000000000001"
QUESTION = "What are the best AI marketing strategies?"
LLM_ANSWER = "Focus on content personalization and automated workflows."


def _ctx(db, params=None):
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=LLM_ANSWER)
    return AgentContext(
        org_id=ORG_ID,
        run_id="run-1",
        params={"question": QUESTION} if params is None else params,
        config={},
        db=db,
        llm=llm,
    )


def _mock_db(chunk_rows=None):
    db = MagicMock()
    if chunk_rows is None:
        chunk_rows = [
            ("AI marketing automates content creation", "brand_guide.pdf"),
            ("Personalization increases engagement by 80%", "research.pdf"),
        ]

    chunks_result = MagicMock()
    mock_rows = []
    for text, source in chunk_rows:
        row = MagicMock()
        row.__getitem__ = lambda self, i, t=text, s=source: [t, s][i]
        mock_rows.append(row)
    chunks_result.fetchall = MagicMock(return_value=mock_rows)

    prompt_result = MagicMock()
    prompt_row = MagicMock()
    prompt_row.__getitem__ = lambda self, i: ["Answer QUESTION using CONTEXT"][i]
    prompt_result.fetchone = MagicMock(return_value=prompt_row)

    async def side_effect(query, params=None):
        sql = str(query)
        if "knowledge_chunks" in sql:
            return chunks_result
        if "prompts" in sql:
            return prompt_result
        return MagicMock()

    db.execute = AsyncMock(side_effect=side_effect)
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_missing_question_fails():
    from agents.knowledge.ai_assistant import AIAssistantAgent
    db = _mock_db()
    result = await AIAssistantAgent().execute(_ctx(db, {}))
    assert result.status == "failed"
    assert "question" in result.error


@pytest.mark.asyncio
async def test_success():
    from agents.knowledge.ai_assistant import AIAssistantAgent
    db = _mock_db()
    result = await AIAssistantAgent().execute(_ctx(db))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_answer_in_output():
    from agents.knowledge.ai_assistant import AIAssistantAgent
    db = _mock_db()
    result = await AIAssistantAgent().execute(_ctx(db))
    assert result.data["answer"] == LLM_ANSWER


@pytest.mark.asyncio
async def test_question_echoed_in_output():
    from agents.knowledge.ai_assistant import AIAssistantAgent
    db = _mock_db()
    result = await AIAssistantAgent().execute(_ctx(db))
    assert result.data["question"] == QUESTION


@pytest.mark.asyncio
async def test_sources_used_count():
    from agents.knowledge.ai_assistant import AIAssistantAgent
    db = _mock_db()
    result = await AIAssistantAgent().execute(_ctx(db))
    assert result.data["sources_used"] == 2


@pytest.mark.asyncio
async def test_no_chunks_still_succeeds():
    from agents.knowledge.ai_assistant import AIAssistantAgent
    db = _mock_db(chunk_rows=[])
    result = await AIAssistantAgent().execute(_ctx(db))
    assert result.status == "success"
    assert result.data["sources_used"] == 0


@pytest.mark.asyncio
async def test_db_query_failure_handled_gracefully():
    from agents.knowledge.ai_assistant import AIAssistantAgent
    db = MagicMock()
    prompt_result = MagicMock()
    prompt_row = MagicMock()
    prompt_row.__getitem__ = lambda self, i: ["Answer QUESTION using CONTEXT"][i]
    prompt_result.fetchone = MagicMock(return_value=prompt_row)

    async def side_effect(query, params=None):
        sql = str(query)
        if "knowledge_chunks" in sql:
            raise Exception("DB error")
        if "prompts" in sql:
            return prompt_result
        return MagicMock()

    db.execute = AsyncMock(side_effect=side_effect)
    db.flush = AsyncMock()
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=LLM_ANSWER)
    ctx = AgentContext(org_id=ORG_ID, run_id="run-1", params={"question": QUESTION}, config={}, db=db, llm=llm)
    result = await AIAssistantAgent().execute(ctx)
    assert result.status == "success"


@pytest.mark.asyncio
async def test_custom_top_k():
    from agents.knowledge.ai_assistant import AIAssistantAgent
    db = _mock_db()
    ctx = _ctx(db, {"question": QUESTION, "top_k": 3})
    result = await AIAssistantAgent().execute(ctx)
    assert result.status == "success"


@pytest.mark.asyncio
async def test_status_in_output():
    from agents.knowledge.ai_assistant import AIAssistantAgent
    db = _mock_db()
    result = await AIAssistantAgent().execute(_ctx(db))
    assert result.data["status"] == "success"
