"""Unit tests for KeywordValidatorAgent."""
import json
import pathlib
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.seo.keyword_validator  # noqa: F401 — triggers @register

from agents.seo.keyword_validator import (
    KeywordValidatorAgent,
    _parse_validation_json,
    _should_hard_archive,
)
from core.agent_base import AgentContext
from core.prompt_registry import PromptNotFoundError, PromptRegistry
from integrations.base import IntegrationError
from integrations.dataforseo import DataForSEOIntegration

# ── Golden trace ──────────────────────────────────────────────────────────────

_TRACE = json.loads(
    (
        pathlib.Path(__file__).parent.parent.parent.parent
        / "golden_traces"
        / "keyword_validator_trace.json"
    ).read_text()
)
_KW_ROWS: list[dict] = _TRACE["mock_keyword_rows"]
_KW_IDS: list[str] = [r["id"] for r in _KW_ROWS]
_MOCK_LLM_RESPONSE: str = _TRACE["mock_llm_response"]
_EXPECTED: dict = _TRACE["expected_result"]["data"]


# ── DB mock factory ───────────────────────────────────────────────────────────

def _make_db(
    keyword_rows: list[dict] | None = None,
    status_counts: dict[str, int] | None = None,
) -> AsyncMock:
    """Return an AsyncSession mock that serves keyword rows and status counts."""
    rows = keyword_rows if keyword_rows is not None else _KW_ROWS
    counts = status_counts if status_counts is not None else {"validated": 2, "archived": 1}

    def _side_effect(query, params=None):
        sql = str(query)
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_result.fetchone.return_value = None

        mock_mappings = MagicMock()
        mock_mappings.all.return_value = []
        mock_result.mappings.return_value = mock_mappings

        if "status = 'raw'" in sql:
            mock_mappings.all.return_value = rows
        elif "group by status" in sql.lower():
            mock_result.fetchall.return_value = list(counts.items())

        return mock_result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side_effect)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db() -> AsyncMock:
    return _make_db()


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=_MOCK_LLM_RESPONSE)
    llm.last_tokens_used = 200
    llm.last_cost_usd = 0.0004
    return llm


@pytest.fixture
def ctx(mock_db: AsyncMock, mock_llm: MagicMock) -> AgentContext:
    return AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000099",
        params={"keyword_ids": _KW_IDS},
        config={},
        db=mock_db,
        llm=mock_llm,
    )


# ── Patch helpers ─────────────────────────────────────────────────────────────

@contextmanager
def _patch_prompt(template: str = "Validate keywords: KEYWORD_BATCH_JSON"):
    with patch.object(PromptRegistry, "get", AsyncMock(return_value=template)):
        yield


@contextmanager
def _patch_dataforseo_unavailable():
    with patch.object(
        DataForSEOIntegration,
        "get_keyword_metrics",
        AsyncMock(side_effect=IntegrationError("no credentials", None, "dataforseo")),
    ):
        yield


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_successful_run_returns_success_status(ctx: AgentContext) -> None:
    with _patch_prompt(), _patch_dataforseo_unavailable():
        result = await KeywordValidatorAgent().run(ctx)

    assert result.status == "success"


async def test_result_includes_all_count_fields(ctx: AgentContext) -> None:
    with _patch_prompt(), _patch_dataforseo_unavailable():
        result = await KeywordValidatorAgent().run(ctx)

    assert result.data["total"] == _EXPECTED["total"]
    assert result.data["validated"] == _EXPECTED["validated"]
    assert result.data["archived"] == _EXPECTED["archived"]


async def test_data_source_is_pending_when_dataforseo_unavailable(ctx: AgentContext) -> None:
    with _patch_prompt(), _patch_dataforseo_unavailable():
        result = await KeywordValidatorAgent().run(ctx)

    assert result.data["data_source"] == "pending"


async def test_data_source_is_dataforseo_when_integration_succeeds(
    ctx: AgentContext,
) -> None:
    mock_metrics = {r["keyword"]: {"volume": 999, "kd": 3.0, "cpc": 2.0} for r in _KW_ROWS}
    with _patch_prompt(), patch.object(
        DataForSEOIntegration,
        "get_keyword_metrics",
        AsyncMock(return_value=mock_metrics),
    ):
        result = await KeywordValidatorAgent().run(ctx)

    assert result.data["data_source"] == "dataforseo"


async def test_metric_update_written_to_db(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    with _patch_prompt(), _patch_dataforseo_unavailable():
        await KeywordValidatorAgent().run(ctx)

    metric_updates = [
        c for c in mock_db.execute.call_args_list
        if c.args and "data_source" in str(c.args[0])
    ]
    assert len(metric_updates) > 0, "Expected metric UPDATE statements in DB"


async def test_agent_run_record_created(ctx: AgentContext, mock_db: AsyncMock) -> None:
    with _patch_prompt(), _patch_dataforseo_unavailable():
        await KeywordValidatorAgent().run(ctx)

    run_inserts = [
        c for c in mock_db.execute.call_args_list
        if c.args and "INSERT INTO agent_runs" in str(c.args[0])
    ]
    assert len(run_inserts) == 1


async def test_no_llm_tokens_used(
    ctx: AgentContext, mock_llm: MagicMock
) -> None:
    with _patch_prompt(), _patch_dataforseo_unavailable():
        result = await KeywordValidatorAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == pytest.approx(0.0)
    mock_llm.complete.assert_not_called()


# ── Empty / no-op cases ───────────────────────────────────────────────────────

async def test_empty_keyword_ids_returns_success_without_llm_call(
    mock_db: AsyncMock, mock_llm: MagicMock
) -> None:
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000099",
        params={"keyword_ids": []},
        config={},
        db=mock_db,
        llm=mock_llm,
    )
    with _patch_prompt(), _patch_dataforseo_unavailable():
        result = await KeywordValidatorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total"] == 0
    mock_llm.complete.assert_not_called()


async def test_no_raw_keywords_found_returns_success(
    mock_llm: MagicMock,
) -> None:
    db = _make_db(keyword_rows=[])  # SELECT returns nothing
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000099",
        params={"keyword_ids": _KW_IDS},
        config={},
        db=db,
        llm=mock_llm,
    )
    with _patch_prompt(), _patch_dataforseo_unavailable():
        result = await KeywordValidatorAgent().run(ctx)

    assert result.status == "success"
    assert result.data["total"] == 0
    mock_llm.complete.assert_not_called()


async def test_no_prompt_needed_agent_succeeds(ctx: AgentContext) -> None:
    """keyword_validator is pure rules — no prompt lookup, no LLM dependency."""
    with (
        patch.object(
            PromptRegistry,
            "get",
            AsyncMock(side_effect=PromptNotFoundError("keyword_validator")),
        ),
        _patch_dataforseo_unavailable(),
    ):
        result = await KeywordValidatorAgent().run(ctx)

    assert result.status == "success"


# ── Hard rules ────────────────────────────────────────────────────────────────

async def test_hard_rule_low_volume_archived_without_llm(
    mock_llm: MagicMock,
) -> None:
    low_volume_rows = [
        {"id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "niche tool",
         "volume": 10, "kd": 2.0, "cpc": 1.0, "intent": "commercial",
         "status": "raw", "data_source": "dataforseo"},
    ]
    db = _make_db(keyword_rows=low_volume_rows, status_counts={"archived": 1})
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000099",
        params={"keyword_ids": ["aaaaaaaa-0000-0000-0000-000000000001"]},
        config={},
        db=db,
        llm=mock_llm,
    )
    with _patch_prompt(), _patch_dataforseo_unavailable():
        result = await KeywordValidatorAgent().run(ctx)

    assert result.status == "success"
    mock_llm.complete.assert_not_called()
    archive_updates = [
        c for c in db.execute.call_args_list
        if c.args and "status = :status" in str(c.args[0])
        and len(c.args) > 1 and "archived" in str(c.args[1])
    ]
    assert len(archive_updates) >= 1


async def test_hard_rule_high_kd_archived_without_llm(
    mock_llm: MagicMock,
) -> None:
    high_kd_rows = [
        {"id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "hard keyword",
         "volume": 5000, "kd": 9.5, "cpc": 3.0, "intent": "commercial",
         "status": "raw", "data_source": "dataforseo"},
    ]
    db = _make_db(keyword_rows=high_kd_rows, status_counts={"archived": 1})
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000099",
        params={"keyword_ids": ["aaaaaaaa-0000-0000-0000-000000000001"]},
        config={},
        db=db,
        llm=mock_llm,
    )
    with _patch_prompt(), _patch_dataforseo_unavailable():
        await KeywordValidatorAgent().run(ctx)

    mock_llm.complete.assert_not_called()


async def test_hard_rule_navigational_intent_archived_without_llm(
    mock_llm: MagicMock,
) -> None:
    nav_rows = [
        {"id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "github login",
         "volume": 2000, "kd": 1.0, "cpc": 0.50, "intent": "navigational", "status": "raw"},
    ]
    db = _make_db(keyword_rows=nav_rows, status_counts={"archived": 1})
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000099",
        params={"keyword_ids": ["aaaaaaaa-0000-0000-0000-000000000001"]},
        config={},
        db=db,
        llm=mock_llm,
    )
    with _patch_prompt(), _patch_dataforseo_unavailable():
        await KeywordValidatorAgent().run(ctx)

    mock_llm.complete.assert_not_called()


async def test_healthy_keyword_validated_without_llm(
    ctx: AgentContext, mock_llm: MagicMock
) -> None:
    with _patch_prompt(), _patch_dataforseo_unavailable():
        await KeywordValidatorAgent().run(ctx)

    mock_llm.complete.assert_not_called()


# ── LLM batch splitting ───────────────────────────────────────────────────────

async def test_large_batch_processed_without_llm(mock_llm: MagicMock) -> None:
    """51 candidates processed by rules only — 0 LLM calls."""
    fifty_one_rows = [
        {
            "id": f"aaaaaaaa-0000-0000-0000-{i:012d}",
            "keyword": f"keyword {i}",
            "volume": 500,
            "kd": 3.0,
            "cpc": 1.5,
            "intent": "commercial",
            "status": "raw",
        }
        for i in range(51)
    ]
    db = _make_db(keyword_rows=fifty_one_rows, status_counts={"validated": 51})
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000099",
        params={"keyword_ids": [r["id"] for r in fifty_one_rows]},
        config={},
        db=db,
        llm=mock_llm,
    )
    with _patch_prompt(), _patch_dataforseo_unavailable():
        result = await KeywordValidatorAgent().run(ctx)

    assert result.status == "success"
    assert mock_llm.complete.call_count == 0


# ── _should_hard_archive unit tests ──────────────────────────────────────────

def test_hard_archive_volume_below_50() -> None:
    assert _should_hard_archive({"volume": 49, "kd": 3.0, "intent": "commercial"})


def test_hard_archive_volume_exactly_50_is_not_archived() -> None:
    assert not _should_hard_archive({"volume": 50, "kd": 3.0, "intent": "commercial"})


def test_hard_archive_kd_above_9() -> None:
    assert _should_hard_archive({"volume": 1000, "kd": 9.1, "intent": "commercial"})


def test_hard_archive_kd_exactly_9_is_not_archived() -> None:
    assert not _should_hard_archive({"volume": 1000, "kd": 9.0, "intent": "commercial"})


def test_hard_archive_navigational_intent() -> None:
    assert _should_hard_archive({"volume": 1000, "kd": 3.0, "intent": "navigational"})


def test_hard_archive_navigational_intent_case_insensitive() -> None:
    assert _should_hard_archive({"volume": 1000, "kd": 3.0, "intent": "Navigational"})


def test_hard_archive_null_volume_does_not_trigger() -> None:
    assert not _should_hard_archive({"volume": None, "kd": 3.0, "intent": "commercial"})


def test_hard_archive_null_kd_does_not_trigger() -> None:
    assert not _should_hard_archive({"volume": 1000, "kd": None, "intent": "commercial"})


def test_hard_archive_healthy_keyword_not_archived() -> None:
    assert not _should_hard_archive({"volume": 500, "kd": 4.0, "intent": "commercial"})


# ── _parse_validation_json unit tests ────────────────────────────────────────

_BATCH = [
    {"id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "ai marketing tools",
     "volume": 1000, "kd": 3.5, "cpc": 4.5, "intent": "commercial"},
    {"id": "aaaaaaaa-0000-0000-0000-000000000002", "keyword": "seo automation",
     "volume": 800, "kd": 4.0, "cpc": 3.2, "intent": "commercial"},
]


def test_parse_clean_json_array() -> None:
    raw = (
        '[{"keyword_id": "aaaaaaaa-0000-0000-0000-000000000001", '
        '"keyword": "ai marketing tools", "worth_targeting": true, "reason": "good"}]'
    )
    result = _parse_validation_json(raw, _BATCH)
    assert len(result) == 1
    assert result[0]["keyword_id"] == "aaaaaaaa-0000-0000-0000-000000000001"
    assert result[0]["worth_targeting"] is True
    assert result[0]["reason"] == "good"


def test_parse_strips_markdown_fence() -> None:
    raw = '```json\n[{"keyword_id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "ai marketing tools", "worth_targeting": false, "reason": "low intent"}]\n```'
    result = _parse_validation_json(raw, _BATCH)
    assert len(result) == 1
    assert result[0]["worth_targeting"] is False


def test_parse_fallback_key_recommended() -> None:
    raw = '[{"keyword_id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "ai marketing tools", "recommended": true, "reason": "good"}]'
    result = _parse_validation_json(raw, _BATCH)
    assert len(result) == 1
    assert result[0]["worth_targeting"] is True


def test_parse_fallback_key_rationale() -> None:
    raw = '[{"keyword_id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "ai marketing tools", "worth_targeting": true, "rationale": "strong signal"}]'
    result = _parse_validation_json(raw, _BATCH)
    assert len(result) == 1
    assert result[0]["reason"] == "strong signal"


def test_parse_match_by_keyword_text_when_id_missing() -> None:
    raw = '[{"keyword": "ai marketing tools", "worth_targeting": true, "reason": "matched by text"}]'
    result = _parse_validation_json(raw, _BATCH)
    assert len(result) == 1
    assert result[0]["keyword_id"] == "aaaaaaaa-0000-0000-0000-000000000001"


def test_parse_match_by_keyword_text_case_insensitive() -> None:
    raw = '[{"keyword": "AI Marketing Tools", "worth_targeting": true, "reason": "upper case"}]'
    result = _parse_validation_json(raw, _BATCH)
    assert len(result) == 1
    assert result[0]["keyword_id"] == "aaaaaaaa-0000-0000-0000-000000000001"


def test_parse_unknown_keyword_skipped() -> None:
    raw = '[{"keyword": "totally unknown topic", "worth_targeting": true, "reason": "???"}]'
    result = _parse_validation_json(raw, _BATCH)
    assert result == []


def test_parse_empty_response_returns_empty_list() -> None:
    assert _parse_validation_json("", _BATCH) == []
    assert _parse_validation_json("   ", _BATCH) == []


def test_parse_model_refusal_returns_empty_list() -> None:
    refusals = [
        "I cannot validate these keywords.",
        "As an AI, I don't have access to this data.",
        "I am unable to complete this request.",
    ]
    for text in refusals:
        assert _parse_validation_json(text, _BATCH) == [], f"expected [] for: {text!r}"


def test_parse_text_surrounding_json() -> None:
    raw = 'Here is my analysis:\n[{"keyword_id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "ai marketing tools", "worth_targeting": true, "reason": "solid"}]\nLet me know if you need more.'
    result = _parse_validation_json(raw, _BATCH)
    assert len(result) == 1


def test_parse_multiple_items() -> None:
    raw = json.dumps([
        {"keyword_id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "ai marketing tools",
         "worth_targeting": True, "reason": "good"},
        {"keyword_id": "aaaaaaaa-0000-0000-0000-000000000002", "keyword": "seo automation",
         "worth_targeting": False, "reason": "too broad"},
    ])
    result = _parse_validation_json(raw, _BATCH)
    assert len(result) == 2
    assert result[0]["worth_targeting"] is True
    assert result[1]["worth_targeting"] is False


def test_parse_trailing_commas() -> None:
    raw = '[{"keyword_id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "ai marketing tools", "worth_targeting": true, "reason": "ok",},]'
    result = _parse_validation_json(raw, _BATCH)
    assert len(result) == 1


def test_parse_code_response_returns_empty_list() -> None:
    code_responses = [
        "function validate(keywords) { return keywords.map(k => ({ ...k, worth_targeting: true })); }",
        "const result = keywords.filter(k => k.volume > 100);\nreturn result;",
        "def validate_keywords(batch):\n    return [{'keyword_id': k['id'], 'worth_targeting': True} for k in batch]",
    ]
    for code in code_responses:
        assert _parse_validation_json(code, _BATCH) == [], f"expected [] for code: {code[:50]!r}"


async def test_llm_parse_failure_applies_hard_rules_fallback(mock_llm: MagicMock) -> None:
    """When LLM returns garbage, hard rules move keywords out of raw — none stay stuck."""
    mock_llm.complete = AsyncMock(return_value="function invalid() { return null; }")
    rows = [
        {"id": "aaaaaaaa-0000-0000-0000-000000000001", "keyword": "ai tools",
         "volume": 500, "kd": 3.0, "cpc": 2.0, "intent": "commercial", "status": "raw"},
        {"id": "aaaaaaaa-0000-0000-0000-000000000002", "keyword": "facebook login",
         "volume": 50000, "kd": 1.0, "cpc": 0.10, "intent": "navigational", "status": "raw"},
    ]
    db = _make_db(keyword_rows=rows, status_counts={"validated": 1, "archived": 1})
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000099",
        params={"keyword_ids": [r["id"] for r in rows]},
        config={},
        db=db,
        llm=mock_llm,
    )
    with _patch_prompt(), _patch_dataforseo_unavailable():
        result = await KeywordValidatorAgent().run(ctx)

    assert result.status == "success"
    status_updates = [
        c for c in db.execute.call_args_list
        if c.args and "status = :status" in str(c.args[0])
    ]
    assert len(status_updates) >= 1, "Expected at least one status UPDATE from hard-rules fallback"
