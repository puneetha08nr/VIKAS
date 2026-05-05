"""Unit tests for strategy_synthesizer agent."""
from __future__ import annotations

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.agent_base import AgentContext, AgentResult

ORG_ID = "00000000-0000-0000-0000-000000000001"

LLM_RESPONSE = json.dumps({
    "summary": "Focus on long-tail AI keywords for Q3",
    "recommendations": [
        {"priority": 1, "action": "Publish 3 articles on AI marketing"},
        {"priority": 2, "action": "Target competitor gaps in email automation"},
    ]
})

OPP_ROW_1 = ("aaa-111", "ai marketing", 0.85, "open")
OPP_ROW_2 = ("bbb-222", "email marketing", 0.72, "open")


def _ctx(db, params=None):
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=LLM_RESPONSE)
    return AgentContext(
        org_id=ORG_ID,
        run_id="run-1",
        params={} if params is None else params,
        config={},
        db=db,
        llm=llm,
    )


def _mock_db(opp_rows=None):
    if opp_rows is None:
        opp_rows = [OPP_ROW_1, OPP_ROW_2]

    db = MagicMock()
    opp_result = MagicMock()
    opp_result.fetchall = MagicMock(return_value=opp_rows)

    prompt_result = MagicMock()
    prompt_row = MagicMock()
    prompt_row.__getitem__ = lambda self, i: [
        "Synthesize strategy from OPPORTUNITIES_JSON count OPPORTUNITY_COUNT"
    ][i]
    prompt_result.fetchone = MagicMock(return_value=prompt_row)

    async def side_effect(query, params=None):
        sql = str(query)
        if "prompts" in sql:
            return prompt_result
        if "opportunities" in sql:
            return opp_result
        return MagicMock()

    db.execute = AsyncMock(side_effect=side_effect)
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_success():
    from agents.orchestration.strategy_synthesizer import StrategySynthesizerAgent
    db = _mock_db()
    result = await StrategySynthesizerAgent().execute(_ctx(db))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_output_has_uuid():
    from agents.orchestration.strategy_synthesizer import StrategySynthesizerAgent
    import uuid
    db = _mock_db()
    result = await StrategySynthesizerAgent().execute(_ctx(db))
    uuid.UUID(result.data["report_id"])


@pytest.mark.asyncio
async def test_opportunities_analyzed():
    from agents.orchestration.strategy_synthesizer import StrategySynthesizerAgent
    db = _mock_db()
    result = await StrategySynthesizerAgent().execute(_ctx(db))
    assert result.data["opportunities_analyzed"] == 2


@pytest.mark.asyncio
async def test_recommendations_count():
    from agents.orchestration.strategy_synthesizer import StrategySynthesizerAgent
    db = _mock_db()
    result = await StrategySynthesizerAgent().execute(_ctx(db))
    assert result.data["recommendations_count"] == 2


@pytest.mark.asyncio
async def test_db_insert_called():
    from agents.orchestration.strategy_synthesizer import StrategySynthesizerAgent
    db = _mock_db()
    await StrategySynthesizerAgent().execute(_ctx(db))
    calls = [str(c.args[0]) for c in db.execute.call_args_list if "strategy_reports" in str(c.args[0])]
    assert len(calls) >= 1


@pytest.mark.asyncio
async def test_db_flush_called():
    from agents.orchestration.strategy_synthesizer import StrategySynthesizerAgent
    db = _mock_db()
    await StrategySynthesizerAgent().execute(_ctx(db))
    db.flush.assert_called()


@pytest.mark.asyncio
async def test_empty_opportunities():
    from agents.orchestration.strategy_synthesizer import StrategySynthesizerAgent
    db = _mock_db(opp_rows=[])
    result = await StrategySynthesizerAgent().execute(_ctx(db))
    assert result.status == "success"
    assert result.data["opportunities_analyzed"] == 0


@pytest.mark.asyncio
async def test_custom_limit():
    from agents.orchestration.strategy_synthesizer import StrategySynthesizerAgent
    db = _mock_db()
    result = await StrategySynthesizerAgent().execute(_ctx(db, {"limit": 5}))
    assert result.status == "success"


@pytest.mark.asyncio
async def test_fallback_on_plain_text():
    from agents.orchestration.strategy_synthesizer import StrategySynthesizerAgent
    db = _mock_db()
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="Focus on AI content this quarter")
    ctx = AgentContext(org_id=ORG_ID, run_id="run-1", params={}, config={}, db=db, llm=llm)
    result = await StrategySynthesizerAgent().execute(ctx)
    assert result.status == "success"
    assert result.data["recommendations_count"] == 0


@pytest.mark.asyncio
async def test_status_in_output():
    from agents.orchestration.strategy_synthesizer import StrategySynthesizerAgent
    db = _mock_db()
    result = await StrategySynthesizerAgent().execute(_ctx(db))
    assert result.data["status"] == "success"
