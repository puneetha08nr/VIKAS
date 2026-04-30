"""Unit tests for KeywordResearchAgent."""
import json
import pathlib
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Register the agent by importing the module
import agents.seo.keyword_research  # noqa: F401

from agents.seo.keyword_research import (
    KeywordResearchAgent,
    _parse_keyword_json,
)
from core.agent_base import AgentContext, AgentResult
from core.prompt_registry import PromptNotFoundError
from core.prompt_registry import PromptRegistry
from rag.brand_voice import BrandVoiceLoader, BrandVoiceNotFoundError

# ── Golden trace ──────────────────────────────────────────────────────────────

_TRACE = json.loads(
    (
        pathlib.Path(__file__).parent.parent.parent.parent
        / "golden_traces"
        / "keyword_research_trace.json"
    ).read_text()
)
_MOCK_LLM_RESPONSE: str = _TRACE["mock_llm_response"]
_EXPECTED_KEYWORD_COUNT: int = _TRACE["expected_result"]["data"]["keywords_found"]


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=_MOCK_LLM_RESPONSE)
    llm.last_tokens_used = 150
    llm.last_cost_usd = 0.0003
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


# ── Patch helpers ─────────────────────────────────────────────────────────────

@contextmanager
def _patch_prompt(template: str = "You are a keyword research specialist..."):
    with patch.object(PromptRegistry, "get", AsyncMock(return_value=template)):
        yield


@contextmanager
def _patch_brand_voice(text: str = "Tone: professional."):
    with patch.object(BrandVoiceLoader, "format_for_prompt", AsyncMock(return_value=text)):
        yield


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_successful_run_returns_success_status(ctx: AgentContext) -> None:
    with _patch_prompt(), _patch_brand_voice():
        result = await KeywordResearchAgent().run(ctx)

    assert result.status == "success"


async def test_keywords_found_count_matches_llm_response(ctx: AgentContext) -> None:
    with _patch_prompt(), _patch_brand_voice():
        result = await KeywordResearchAgent().run(ctx)

    assert result.data["keywords_found"] == _EXPECTED_KEYWORD_COUNT


async def test_seed_keyword_echoed_in_result(ctx: AgentContext) -> None:
    with _patch_prompt(), _patch_brand_voice():
        result = await KeywordResearchAgent().run(ctx)

    assert result.data["seed"] == "ai marketing"


async def test_keywords_written_to_db(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    with _patch_prompt(), _patch_brand_voice():
        await KeywordResearchAgent().run(ctx)

    insert_calls = [
        c for c in mock_db.execute.call_args_list
        if c.args and "INSERT INTO keywords" in str(c.args[0])
    ]
    assert len(insert_calls) == _EXPECTED_KEYWORD_COUNT


async def test_agent_run_record_created(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    with _patch_prompt(), _patch_brand_voice():
        await KeywordResearchAgent().run(ctx)

    run_inserts = [
        c for c in mock_db.execute.call_args_list
        if c.args and "INSERT INTO agent_runs" in str(c.args[0])
    ]
    assert len(run_inserts) == 1


async def test_tokens_and_cost_from_llm_in_result(
    ctx: AgentContext, mock_llm: MagicMock
) -> None:
    mock_llm.last_tokens_used = 250
    mock_llm.last_cost_usd = 0.0006

    with _patch_prompt(), _patch_brand_voice():
        result = await KeywordResearchAgent().run(ctx)

    assert result.tokens_used == 250
    assert result.cost_usd == pytest.approx(0.0006)


# ── Missing prompt ────────────────────────────────────────────────────────────

async def test_missing_prompt_results_in_failed_status(ctx: AgentContext) -> None:
    """PromptNotFoundError must surface as a failed AgentResult — not crash the process."""
    with patch.object(
        PromptRegistry, "get", AsyncMock(side_effect=PromptNotFoundError("keyword_research"))
    ):
        result = await KeywordResearchAgent().run(ctx)

    assert result.status == "failed"
    assert "keyword_research" in (result.error or "")


async def test_missing_prompt_error_message_is_descriptive(ctx: AgentContext) -> None:
    with patch.object(
        PromptRegistry, "get", AsyncMock(side_effect=PromptNotFoundError("keyword_research"))
    ):
        result = await KeywordResearchAgent().run(ctx)

    assert result.error is not None
    assert len(result.error) > 10  # not an empty string


# ── Brand voice missing ───────────────────────────────────────────────────────

async def test_missing_brand_voice_does_not_crash(ctx: AgentContext) -> None:
    with (
        _patch_prompt(),
        patch.object(
            BrandVoiceLoader,
            "format_for_prompt",
            AsyncMock(side_effect=BrandVoiceNotFoundError("org-1")),
        ),
    ):
        result = await KeywordResearchAgent().run(ctx)

    assert result.status == "success"


# ── _parse_keyword_json unit tests ────────────────────────────────────────────

def test_parse_clean_json_array() -> None:
    raw = '[{"keyword": "seo tips", "volume": 1000}]'
    result = _parse_keyword_json(raw)
    assert len(result) == 1
    assert result[0]["keyword"] == "seo tips"


def test_parse_json_in_markdown_fence() -> None:
    raw = "```json\n[{\"keyword\": \"content marketing\"}]\n```"
    result = _parse_keyword_json(raw)
    assert len(result) == 1
    assert result[0]["keyword"] == "content marketing"


def test_parse_invalid_json_returns_empty_list() -> None:
    result = _parse_keyword_json("Sorry, I cannot provide that.")
    assert result == []


def test_parse_filters_non_dict_items() -> None:
    raw = '[{"keyword": "good"}, "not a dict", 42, {"keyword": "also good"}]'
    result = _parse_keyword_json(raw)
    assert len(result) == 2


def test_parse_empty_string_returns_empty_list() -> None:
    assert _parse_keyword_json("") == []


def test_parse_full_golden_trace_response() -> None:
    result = _parse_keyword_json(_MOCK_LLM_RESPONSE)
    assert len(result) == _EXPECTED_KEYWORD_COUNT
    assert all("keyword" in kw for kw in result)
