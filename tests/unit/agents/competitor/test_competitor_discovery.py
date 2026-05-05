"""Unit tests for competitor_discovery agent."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from core.agent_base import AgentContext, AgentResult

ORG_ID = "00000000-0000-0000-0000-000000000001"
KEYWORD = "ai marketing tools"

LLM_RESPONSE = '[{"domain": "hubspot.com"}, {"domain": "marketo.com"}, {"domain": "activecampaign.com"}]'


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
    prompt_row.__getitem__ = lambda self, i: ["Find competitor domains for KEYWORD"][i]
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
    from agents.competitor.competitor_discovery import CompetitorDiscoveryAgent
    db = _mock_db()
    result = await CompetitorDiscoveryAgent().execute(_ctx(db, {}))
    assert result.status == "failed"
    assert "keyword" in result.error


@pytest.mark.asyncio
async def test_success():
    from agents.competitor.competitor_discovery import CompetitorDiscoveryAgent
    db = _mock_db()
    result = await CompetitorDiscoveryAgent().execute(_ctx(db))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_competitors_found_count():
    from agents.competitor.competitor_discovery import CompetitorDiscoveryAgent
    db = _mock_db()
    result = await CompetitorDiscoveryAgent().execute(_ctx(db))
    assert result.data["competitors_found"] == 3


@pytest.mark.asyncio
async def test_keyword_in_output():
    from agents.competitor.competitor_discovery import CompetitorDiscoveryAgent
    db = _mock_db()
    result = await CompetitorDiscoveryAgent().execute(_ctx(db))
    assert result.data["seed_keyword"] == KEYWORD


@pytest.mark.asyncio
async def test_db_insert_called_per_domain():
    from agents.competitor.competitor_discovery import CompetitorDiscoveryAgent
    db = _mock_db()
    await CompetitorDiscoveryAgent().execute(_ctx(db))
    calls = [str(c.args[0]) for c in db.execute.call_args_list if "competitors" in str(c.args[0])]
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_db_flush_called():
    from agents.competitor.competitor_discovery import CompetitorDiscoveryAgent
    db = _mock_db()
    await CompetitorDiscoveryAgent().execute(_ctx(db))
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_fallback_on_plain_text():
    from agents.competitor.competitor_discovery import CompetitorDiscoveryAgent
    db = _mock_db()
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="hubspot.com\nmarketo.com\nactivecampaign.com")
    ctx = AgentContext(org_id=ORG_ID, run_id="run-1", params={"keyword": KEYWORD}, config={}, db=db, llm=llm)
    result = await CompetitorDiscoveryAgent().execute(ctx)
    assert result.status == "success"
    assert result.data["competitors_found"] == 3


@pytest.mark.asyncio
async def test_insert_failure_handled_gracefully():
    from agents.competitor.competitor_discovery import CompetitorDiscoveryAgent
    db = _mock_db()
    call_count = 0

    async def side_effect_raise(query, params=None):
        nonlocal call_count
        sql = str(query)
        if "prompts" in sql:
            result = MagicMock()
            row = MagicMock()
            row.__getitem__ = lambda self, i: ["Find competitor domains for KEYWORD"][i]
            result.fetchone = MagicMock(return_value=row)
            return result
        if "competitors" in sql:
            call_count += 1
            raise Exception("DB error")
        return MagicMock()

    db.execute = AsyncMock(side_effect=side_effect_raise)
    result = await CompetitorDiscoveryAgent().execute(_ctx(db))
    assert result.status == "success"
    assert result.data["competitors_written"] == 0
