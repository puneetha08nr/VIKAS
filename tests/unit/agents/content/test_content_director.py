"""Unit tests for content_director agent."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.agent_base import AgentContext, AgentResult

ORG_ID = "00000000-0000-0000-0000-000000000001"
OPP_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PLAN_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
ARTICLE_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
LI_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
TW_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
NL_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
VS_ID = "11111111-1111-1111-1111-111111111111"


def _ctx(db, params=None):
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="")
    return AgentContext(
        org_id=ORG_ID,
        run_id="run-1",
        params={"opportunity_id": OPP_ID} if params is None else params,
        config={},
        db=db,
        llm=llm,
    )


def _make_sub_result(name, data):
    return AgentResult(status="success", data=data)


def _make_failed_result(error):
    return AgentResult(status="failed", error=error)


@pytest.fixture
def mock_registry():
    plan_result = AgentResult(status="success", data={"article_plan_id": PLAN_ID})
    write_result = AgentResult(status="success", data={"article_id": ARTICLE_ID})
    li_result = AgentResult(status="success", data={"linkedin_post_id": LI_ID})
    tw_result = AgentResult(status="success", data={"twitter_thread_id": TW_ID})
    nl_result = AgentResult(status="success", data={"newsletter_id": NL_ID})
    vs_result = AgentResult(status="success", data={"video_script_id": VS_ID})

    agents = {
        "article_planner": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=plan_result))),
        "article_writer": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=write_result))),
        "linkedin_agent": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=li_result))),
        "twitter_agent": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=tw_result))),
        "newsletter_agent": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=nl_result))),
        "video_scriptwriter": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=vs_result))),
    }
    return agents


@pytest.mark.asyncio
async def test_missing_opportunity_id_fails():
    from agents.content.content_director import ContentDirectorAgent
    db = MagicMock()
    agent = ContentDirectorAgent()
    result = await agent.execute(_ctx(db, {}))
    assert result.status == "failed"
    assert "opportunity_id" in result.error


@pytest.mark.asyncio
async def test_success_all_stages(mock_registry):
    from agents.content.content_director import ContentDirectorAgent
    db = MagicMock()
    with patch("agents.content.content_director.REGISTRY", mock_registry):
        agent = ContentDirectorAgent()
        result = await agent.execute(_ctx(db))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_output_contains_all_ids(mock_registry):
    from agents.content.content_director import ContentDirectorAgent
    db = MagicMock()
    with patch("agents.content.content_director.REGISTRY", mock_registry):
        agent = ContentDirectorAgent()
        result = await agent.execute(_ctx(db))
    assert result.data["article_plan_id"] == PLAN_ID
    assert result.data["article_id"] == ARTICLE_ID
    assert result.data["linkedin_post_id"] == LI_ID
    assert result.data["twitter_thread_id"] == TW_ID
    assert result.data["newsletter_id"] == NL_ID
    assert result.data["video_script_id"] == VS_ID


@pytest.mark.asyncio
async def test_partial_status_on_planner_failure():
    from agents.content.content_director import ContentDirectorAgent
    db = MagicMock()
    failed = AgentResult(status="failed", error="planner broken")
    agents = {
        "article_planner": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=failed))),
        "article_writer": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=AgentResult(status="success", data={})))),
        "linkedin_agent": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=AgentResult(status="success", data={})))),
        "twitter_agent": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=AgentResult(status="success", data={})))),
        "newsletter_agent": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=AgentResult(status="success", data={})))),
        "video_scriptwriter": MagicMock(return_value=MagicMock(execute=AsyncMock(return_value=AgentResult(status="success", data={})))),
    }
    with patch("agents.content.content_director.REGISTRY", agents):
        agent = ContentDirectorAgent()
        result = await agent.execute(_ctx(db))
    assert result.data["status"] == "partial"


@pytest.mark.asyncio
async def test_partial_status_on_social_failure(mock_registry):
    from agents.content.content_director import ContentDirectorAgent
    db = MagicMock()
    mock_registry["linkedin_agent"] = MagicMock(
        return_value=MagicMock(execute=AsyncMock(return_value=AgentResult(status="failed", error="li broke")))
    )
    with patch("agents.content.content_director.REGISTRY", mock_registry):
        agent = ContentDirectorAgent()
        result = await agent.execute(_ctx(db))
    assert result.data["status"] == "partial"


@pytest.mark.asyncio
async def test_unknown_sub_agent_fails_gracefully():
    from agents.content.content_director import ContentDirectorAgent
    db = MagicMock()
    # Registry missing all agents
    with patch("agents.content.content_director.REGISTRY", {}):
        agent = ContentDirectorAgent()
        result = await agent.execute(_ctx(db))
    assert result.status == "success"  # director always returns success
    assert result.data["status"] == "partial"


@pytest.mark.asyncio
async def test_opportunity_id_passed_to_planner(mock_registry):
    from agents.content.content_director import ContentDirectorAgent
    db = MagicMock()
    with patch("agents.content.content_director.REGISTRY", mock_registry):
        agent = ContentDirectorAgent()
        await agent.execute(_ctx(db))
    planner_instance = mock_registry["article_planner"].return_value
    call_args = planner_instance.execute.call_args
    ctx_arg = call_args[0][0]
    assert ctx_arg.params.get("opportunity_id") == OPP_ID


@pytest.mark.asyncio
async def test_article_id_passed_to_social_agents(mock_registry):
    from agents.content.content_director import ContentDirectorAgent
    db = MagicMock()
    with patch("agents.content.content_director.REGISTRY", mock_registry):
        agent = ContentDirectorAgent()
        await agent.execute(_ctx(db))
    li_instance = mock_registry["linkedin_agent"].return_value
    call_args = li_instance.execute.call_args
    ctx_arg = call_args[0][0]
    # linkedin_agent now receives article_plan_id (from plan outline — cheaper)
    assert (
        ctx_arg.params.get("article_plan_id") == PLAN_ID
        or ctx_arg.params.get("article_id") == ARTICLE_ID
    )
