"""Unit tests for KeywordResearchAgent."""
import json
import pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Register the agent by importing the module
import agents.seo.keyword_research  # noqa: F401

from agents.seo.keyword_research import KeywordResearchAgent
from core.agent_base import AgentContext
from integrations.base import IntegrationError

# ── Golden trace ──────────────────────────────────────────────────────────────

_TRACE = json.loads(
    (
        pathlib.Path(__file__).parent.parent.parent.parent
        / "golden_traces"
        / "keyword_research_trace.json"
    ).read_text()
)
_MOCK_KEYWORDS: list[dict] = json.loads(_TRACE["mock_llm_response"])
_EXPECTED_KEYWORD_COUNT: int = _TRACE["expected_result"]["data"]["keywords_found"]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.rowcount = 1
    db.execute = AsyncMock(return_value=mock_result)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value="")
    llm.last_tokens_used = 0
    llm.last_cost_usd = 0.0
    return llm


@pytest.fixture
def ctx(mock_db: AsyncMock, mock_llm: MagicMock) -> AgentContext:
    return AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        params={"seed_keyword": "ai marketing"},
        config={},
        db=mock_db,
        llm=mock_llm,
    )


# ── Patch helper ──────────────────────────────────────────────────────────────

def _patch_dataforseo(keywords: list[dict] | None = None):
    kws = keywords if keywords is not None else _MOCK_KEYWORDS
    return patch(
        "agents.seo.keyword_research.DataForSEOIntegration",
        **{"return_value.get_keyword_ideas": AsyncMock(return_value=kws)},
    )


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_successful_run_returns_success_status(ctx: AgentContext) -> None:
    with _patch_dataforseo():
        result = await KeywordResearchAgent().run(ctx)

    assert result.status == "success"


async def test_keywords_found_count_matches_golden_trace(ctx: AgentContext) -> None:
    with _patch_dataforseo():
        result = await KeywordResearchAgent().run(ctx)

    assert result.data["keywords_found"] == _EXPECTED_KEYWORD_COUNT


async def test_seed_keyword_echoed_in_result(ctx: AgentContext) -> None:
    with _patch_dataforseo():
        result = await KeywordResearchAgent().run(ctx)

    assert result.data["seed"] == "ai marketing"


async def test_keywords_written_to_db(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    with _patch_dataforseo():
        await KeywordResearchAgent().run(ctx)

    insert_calls = [
        c for c in mock_db.execute.call_args_list
        if c.args and "INSERT INTO keywords" in str(c.args[0])
    ]
    assert len(insert_calls) == _EXPECTED_KEYWORD_COUNT


async def test_agent_run_record_created(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    with _patch_dataforseo():
        await KeywordResearchAgent().run(ctx)

    run_inserts = [
        c for c in mock_db.execute.call_args_list
        if c.args and "INSERT INTO agent_runs" in str(c.args[0])
    ]
    assert len(run_inserts) == 1


async def test_dataforseo_agent_uses_no_llm_tokens(ctx: AgentContext) -> None:
    with _patch_dataforseo():
        result = await KeywordResearchAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


async def test_data_source_is_dataforseo(ctx: AgentContext) -> None:
    with _patch_dataforseo():
        result = await KeywordResearchAgent().run(ctx)

    assert result.data.get("data_source") == "dataforseo"


# ── Empty results ─────────────────────────────────────────────────────────────

async def test_empty_dataforseo_response_returns_partial_status(
    ctx: AgentContext,
) -> None:
    with _patch_dataforseo(keywords=[]):
        result = await KeywordResearchAgent().run(ctx)

    assert result.status == "partial"
    assert result.data["keywords_found"] == 0


# ── Integration error ─────────────────────────────────────────────────────────

async def test_dataforseo_error_results_in_failed_status(ctx: AgentContext) -> None:
    with patch(
        "agents.seo.keyword_research.DataForSEOIntegration",
        **{
            "return_value.get_keyword_ideas": AsyncMock(
                side_effect=IntegrationError(
                    "Credentials not configured",
                    status_code=None,
                    integration_name="dataforseo",
                )
            )
        },
    ):
        result = await KeywordResearchAgent().run(ctx)

    assert result.status == "failed"
    assert result.error is not None
    assert len(result.error) > 10


async def test_dataforseo_error_message_is_descriptive(ctx: AgentContext) -> None:
    with patch(
        "agents.seo.keyword_research.DataForSEOIntegration",
        **{
            "return_value.get_keyword_ideas": AsyncMock(
                side_effect=IntegrationError(
                    "Credentials not configured",
                    status_code=None,
                    integration_name="dataforseo",
                )
            )
        },
    ):
        result = await KeywordResearchAgent().run(ctx)

    assert result.error is not None
    assert "DataForSEO" in result.error or "dataforseo" in result.error.lower()


# ── Missing seed keyword ──────────────────────────────────────────────────────

async def test_missing_seed_keyword_results_in_failed_status(
    mock_db: AsyncMock, mock_llm: MagicMock
) -> None:
    ctx_no_seed = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        params={},
        config={},
        db=mock_db,
        llm=mock_llm,
    )
    result = await KeywordResearchAgent().run(ctx_no_seed)

    assert result.status == "failed"
    assert "seed_keyword" in (result.error or "")


# ── _parse_keyword_json / _normalise tests removed ───────────────────────────
# keyword_research was refactored to use DataForSEO directly (no LLM needed).
# Both helpers (_parse_keyword_json, _normalise) no longer exist in the module.
