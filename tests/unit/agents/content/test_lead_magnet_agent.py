"""Unit tests for lead_magnet_agent."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.agent_base import AgentContext, AgentResult

ORG_ID = "00000000-0000-0000-0000-000000000001"
KEYWORD = "email marketing automation"

LLM_RESPONSE = '{"title": "Email Marketing Automation Checklist", "body": "1. Set up welcome sequence\\n2. Segment your list"}'


def _ctx(db, params=None):
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=LLM_RESPONSE)
    return AgentContext(
        org_id=ORG_ID,
        run_id="run-1",
        params={"keyword": KEYWORD} if params is None else params,
        config={},
        db=db,
        llm=llm,
    )


def _mock_db():
    db = MagicMock()
    prompt_result = MagicMock()
    prompt_row = MagicMock()
    prompt_row.__getitem__ = lambda self, i: ["Create a FORMAT lead magnet for KEYWORD"][i]
    prompt_result.fetchone = MagicMock(return_value=prompt_row)

    async def side_effect(query, params=None):
        sql = str(query)
        if "prompts" in sql:
            return prompt_result
        return MagicMock()

    db.execute = AsyncMock(side_effect=side_effect)
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_missing_keyword_fails():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    db = _mock_db()
    result = await LeadMagnetAgent().execute(_ctx(db, {}))
    assert result.status == "failed"
    assert "keyword" in result.error


@pytest.mark.asyncio
async def test_success():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    db = _mock_db()
    result = await LeadMagnetAgent().execute(_ctx(db))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_output_has_uuid():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    import uuid
    db = _mock_db()
    result = await LeadMagnetAgent().execute(_ctx(db))
    uuid.UUID(result.data["lead_magnet_id"])


@pytest.mark.asyncio
async def test_keyword_in_output():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    db = _mock_db()
    result = await LeadMagnetAgent().execute(_ctx(db))
    assert result.data["keyword"] == KEYWORD


@pytest.mark.asyncio
async def test_default_format_is_checklist():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    db = _mock_db()
    result = await LeadMagnetAgent().execute(_ctx(db, {"keyword": KEYWORD}))
    assert result.data["format"] == "checklist"


@pytest.mark.asyncio
async def test_custom_format_ebook():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    db = _mock_db()
    result = await LeadMagnetAgent().execute(_ctx(db, {"keyword": KEYWORD, "format": "ebook"}))
    assert result.data["format"] == "ebook"


@pytest.mark.asyncio
async def test_invalid_format_defaults_to_checklist():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    db = _mock_db()
    result = await LeadMagnetAgent().execute(_ctx(db, {"keyword": KEYWORD, "format": "brochure"}))
    assert result.data["format"] == "checklist"


@pytest.mark.asyncio
async def test_db_insert_called():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    db = _mock_db()
    await LeadMagnetAgent().execute(_ctx(db))
    calls = [str(c.args[0]) for c in db.execute.call_args_list if "lead_magnets" in str(c.args[0])]
    assert len(calls) >= 1


@pytest.mark.asyncio
async def test_db_flush_called():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    db = _mock_db()
    await LeadMagnetAgent().execute(_ctx(db))
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_fallback_on_plain_text():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    db = _mock_db()
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="Plain text checklist content")
    ctx = AgentContext(org_id=ORG_ID, run_id="run-1", params={"keyword": KEYWORD}, config={}, db=db, llm=llm)
    result = await LeadMagnetAgent().execute(ctx)
    assert result.status == "success"


@pytest.mark.asyncio
async def test_status_draft():
    from agents.content.lead_magnet_agent import LeadMagnetAgent
    db = _mock_db()
    result = await LeadMagnetAgent().execute(_ctx(db))
    assert result.data["status"] == "draft"
