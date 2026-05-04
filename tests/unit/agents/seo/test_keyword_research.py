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
    _normalise,
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


# ── Format coverage: 14 formats ───────────────────────────────────────────────

def test_format1_clean_object_array() -> None:
    raw = '[{"keyword": "seo tools", "volume": 1000, "kd": 4.5, "cpc": 2.30, "intent": "commercial"}]'
    result = _parse_keyword_json(raw)
    assert len(result) == 1
    assert result[0]["keyword"] == "seo tools"
    assert result[0]["volume"] == 1000
    assert result[0]["kd"] == pytest.approx(4.5)
    assert result[0]["intent"] == "commercial"


def test_format2_mixed_strings_and_objects() -> None:
    # strings are treated as duplicate labels; dicts carry the real data
    raw = '["seo tools", {"keyword": "seo tools", "volume": 1000}, {"keyword": "content marketing", "volume": 800}]'
    result = _parse_keyword_json(raw)
    assert len(result) == 2
    keywords = {r["keyword"] for r in result}
    assert "seo tools" in keywords
    assert "content marketing" in keywords


def test_format3_raw_objects_no_array_wrapper() -> None:
    raw = '{"keyword": "seo tools", "volume": 1000}\n{"keyword": "content marketing", "volume": 800}'
    result = _parse_keyword_json(raw)
    assert len(result) == 2
    keywords = {r["keyword"] for r in result}
    assert "seo tools" in keywords
    assert "content marketing" in keywords


def test_format4_plain_string_array() -> None:
    raw = '["seo tools", "content marketing", "email marketing"]'
    result = _parse_keyword_json(raw)
    assert len(result) == 3
    assert result[0]["keyword"] == "seo tools"
    assert result[1]["keyword"] == "content marketing"


def test_format5_nested_under_keywords_key() -> None:
    raw = '{"keywords": [{"keyword": "seo tools", "volume": 1000}]}'
    result = _parse_keyword_json(raw)
    assert len(result) == 1
    assert result[0]["keyword"] == "seo tools"


def test_format5_nested_under_results_and_data_keys() -> None:
    for key in ["results", "data"]:
        raw = json.dumps({key: [{"keyword": "seo tools", "volume": 1000}]})
        result = _parse_keyword_json(raw)
        assert len(result) == 1, f"failed for key='{key}'"
        assert result[0]["keyword"] == "seo tools"


def test_format6_markdown_code_block() -> None:
    raw = '```json\n[{"keyword": "seo tools", "volume": 1000}]\n```'
    result = _parse_keyword_json(raw)
    assert len(result) == 1
    assert result[0]["keyword"] == "seo tools"


def test_format7_trailing_commas() -> None:
    raw = '[{"keyword": "seo tools", "volume": 1000,},]'
    result = _parse_keyword_json(raw)
    assert len(result) == 1
    assert result[0]["keyword"] == "seo tools"


def test_format8_single_quotes() -> None:
    raw = "[{'keyword': 'seo tools', 'volume': 1000, 'intent': 'commercial'}]"
    result = _parse_keyword_json(raw)
    assert len(result) == 1
    assert result[0]["keyword"] == "seo tools"
    assert result[0]["intent"] == "commercial"


def test_format9_numbers_as_strings() -> None:
    raw = '[{"keyword": "seo tools", "volume": "1000", "kd": "4.5", "cpc": "2.30"}]'
    result = _parse_keyword_json(raw)
    assert len(result) == 1
    assert result[0]["keyword"] == "seo tools"
    assert result[0]["volume"] == 1000
    assert result[0]["kd"] == pytest.approx(4.5)
    assert result[0]["cpc"] == pytest.approx(2.30)


def test_format10_missing_fields_partial_object() -> None:
    raw = '[{"keyword": "seo tools"}, {"keyword": "content marketing", "volume": 1000}]'
    result = _parse_keyword_json(raw)
    assert len(result) == 2
    partial = next(r for r in result if r["keyword"] == "seo tools")
    assert partial["volume"] is None
    assert partial["kd"] is None
    assert partial["cpc"] is None
    full = next(r for r in result if r["keyword"] == "content marketing")
    assert full["volume"] == 1000


def test_format11_text_before_and_after_json() -> None:
    raw = 'Here are the keywords:\n[{"keyword": "seo tools", "volume": 1000}]\nHope this helps!'
    result = _parse_keyword_json(raw)
    assert len(result) == 1
    assert result[0]["keyword"] == "seo tools"


def test_format12_empty_and_whitespace_response() -> None:
    assert _parse_keyword_json("") == []
    assert _parse_keyword_json("   ") == []
    assert _parse_keyword_json("\n\t\n") == []


def test_format13_model_refusal() -> None:
    refusals = [
        "I cannot generate keywords for that topic.",
        "As an AI, I don't have access to real search volume data.",
        "I'm unable to provide keyword research for this query.",
        "I am unable to complete this request.",
    ]
    for text in refusals:
        assert _parse_keyword_json(text) == [], f"expected [] for refusal: {text!r}"


def test_format14_single_object_not_in_array() -> None:
    raw = '{"keyword": "seo tools", "volume": 1000, "kd": 4.5, "intent": "commercial"}'
    result = _parse_keyword_json(raw)
    assert len(result) == 1
    assert result[0]["keyword"] == "seo tools"
    assert result[0]["volume"] == 1000


# ── _normalise unit tests ─────────────────────────────────────────────────────

def test_normalise_coerces_string_numbers() -> None:
    items = [{"keyword": "seo tools", "volume": "1500", "kd": "6.2", "cpc": "3.10"}]
    result = _normalise(items)
    assert result[0]["volume"] == 1500
    assert result[0]["kd"] == pytest.approx(6.2)
    assert result[0]["cpc"] == pytest.approx(3.10)


def test_normalise_handles_alternate_field_names() -> None:
    items = [{"keyword": "seo tools", "search_volume": 900, "keyword_difficulty": 5.5}]
    result = _normalise(items)
    assert result[0]["volume"] == 900
    assert result[0]["kd"] == pytest.approx(5.5)


def test_normalise_skips_items_without_keyword() -> None:
    items = [{"volume": 1000, "kd": 4.5}, {"keyword": "valid kw"}]
    result = _normalise(items)
    assert len(result) == 1
    assert result[0]["keyword"] == "valid kw"


def test_normalise_lowercases_intent() -> None:
    items = [{"keyword": "seo tools", "intent": "Commercial"}]
    result = _normalise(items)
    assert result[0]["intent"] == "commercial"


def test_normalise_returns_none_for_missing_fields() -> None:
    items = [{"keyword": "seo tools"}]
    result = _normalise(items)
    assert result[0]["volume"] is None
    assert result[0]["kd"] is None
    assert result[0]["cpc"] is None
    assert result[0]["intent"] is None
    assert result[0]["reason"] is None
