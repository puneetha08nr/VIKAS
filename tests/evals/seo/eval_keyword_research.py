"""
Evals for keyword_research agent.

SECTION 1 — STRUCTURAL EVAL  (automated, runs in CI)
SECTION 2 — RELEVANCE EVAL   (automated, runs weekly via eval_runner.py)
SECTION 3 — GROUND TRUTH     (manual,    runs monthly via eval_runner.py)
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import agents.seo.keyword_research  # noqa: F401 — registers the agent
from agents.seo.keyword_research import KeywordResearchAgent
from base import GroundTruthSample
from core.agent_base import AgentContext
from core.prompt_registry import PromptNotFoundError, PromptRegistry

AGENT_NAME: str = "keyword_research"
IS_BUILT: bool = True

_MOCK_PROMPT = "Generate keywords for SEED_KEYWORD. Return JSON array."
_VALID_INTENTS = {"informational", "navigational", "commercial", "transactional"}

_MOCK_LLM_RESPONSE = (
    '[{"keyword": "ai marketing tools", "volume": 8100, "kd": 42.0, "cpc": 4.50, "intent": "commercial", "reason": "high value"},'
    ' {"keyword": "ai content marketing strategy", "volume": 3200, "kd": 38.5, "cpc": 5.10, "intent": "informational", "reason": "informational intent"},'
    ' {"keyword": "marketing automation with ai", "volume": 5400, "kd": 35.0, "cpc": 6.20, "intent": "commercial", "reason": "commercial"}]'
)


@contextmanager
def _patch_prompt(template: str = _MOCK_PROMPT):
    with patch.object(PromptRegistry, "get", AsyncMock(return_value=template)):
        yield


def _make_ctx(mock_db: AsyncMock, mock_llm: MagicMock, seed: str = "ai marketing") -> AgentContext:
    return AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000099",
        params={"seed_keyword": seed},
        config={},
        db=mock_db,
        llm=mock_llm,
    )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════

class TestStructural_keyword_research:
    """
    Verifies the output CONTRACT of keyword_research — shape, types, enum values,
    required fields, and that rows land in the DB.
    All checks use mocked DB and LLM (no network calls, no real DB).
    """

    # ── AgentResult shape ─────────────────────────────────────────────────────

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            result = await KeywordResearchAgent().run(ctx)
        assert result.status in {"success", "failed", "partial"}, (
            f"status must be one of success|failed|partial, got {result.status!r}"
        )

    async def test_status_is_success_on_valid_response(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            result = await KeywordResearchAgent().run(ctx)
        assert result.status == "success"

    async def test_keywords_found_is_non_negative_int(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            result = await KeywordResearchAgent().run(ctx)
        kf = result.data.get("keywords_found")
        assert isinstance(kf, int), f"keywords_found must be int, got {type(kf).__name__}"
        assert kf >= 0

    async def test_seed_is_non_empty_string(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm, seed="content marketing")
        with _patch_prompt():
            result = await KeywordResearchAgent().run(ctx)
        seed = result.data.get("seed")
        assert isinstance(seed, str) and seed, "data.seed must be a non-empty string"
        assert seed == "content marketing"

    async def test_tokens_used_is_non_negative_int(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            result = await KeywordResearchAgent().run(ctx)
        assert isinstance(result.tokens_used, int) and result.tokens_used >= 0

    async def test_cost_usd_is_non_negative_float(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            result = await KeywordResearchAgent().run(ctx)
        assert isinstance(result.cost_usd, float) and result.cost_usd >= 0.0

    async def test_error_is_none_on_success(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            result = await KeywordResearchAgent().run(ctx)
        assert result.error is None

    # ── DB writes ─────────────────────────────────────────────────────────────

    async def test_at_least_one_keyword_row_inserted(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            await KeywordResearchAgent().run(ctx)
        inserts = [
            c for c in mock_db.execute.call_args_list
            if c.args and "INSERT INTO keywords" in str(c.args[0])
        ]
        assert len(inserts) >= 1, "Expected at least one INSERT INTO keywords"

    async def test_keyword_insert_count_matches_keywords_found(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            result = await KeywordResearchAgent().run(ctx)
        inserts = [
            c for c in mock_db.execute.call_args_list
            if c.args and "INSERT INTO keywords" in str(c.args[0])
        ]
        assert len(inserts) == result.data["keywords_found"]

    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            await KeywordResearchAgent().run(ctx)
        run_inserts = [
            c for c in mock_db.execute.call_args_list
            if c.args and "INSERT INTO agent_runs" in str(c.args[0])
        ]
        assert len(run_inserts) == 1

    async def test_agent_run_record_updated_with_status(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            await KeywordResearchAgent().run(ctx)
        updates = [
            c for c in mock_db.execute.call_args_list
            if c.args and "UPDATE agent_runs" in str(c.args[0])
        ]
        assert len(updates) >= 1

    # ── Row-level field types and enum values ─────────────────────────────────

    async def test_keyword_insert_params_have_required_columns(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            await KeywordResearchAgent().run(ctx)
        inserts = [
            c for c in mock_db.execute.call_args_list
            if c.args and "INSERT INTO keywords" in str(c.args[0])
        ]
        for call in inserts:
            params = call.args[1]
            assert "keyword" in params, "INSERT missing 'keyword' column"
            assert "org_id" in params, "INSERT missing 'org_id' column"
            assert "source_agent" in params, "INSERT missing 'source_agent' column"

    async def test_keyword_insert_keyword_is_non_empty_string(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            await KeywordResearchAgent().run(ctx)
        inserts = [
            c for c in mock_db.execute.call_args_list
            if c.args and "INSERT INTO keywords" in str(c.args[0])
        ]
        for call in inserts:
            kw = call.args[1].get("keyword", "")
            assert isinstance(kw, str) and kw.strip(), (
                f"keyword must be a non-empty string, got {kw!r}"
            )

    async def test_keyword_insert_source_agent_is_correct(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            await KeywordResearchAgent().run(ctx)
        inserts = [
            c for c in mock_db.execute.call_args_list
            if c.args and "INSERT INTO keywords" in str(c.args[0])
        ]
        for call in inserts:
            assert call.args[1].get("source_agent") == "keyword_research"

    async def test_keyword_insert_intent_is_valid_enum_or_none(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            await KeywordResearchAgent().run(ctx)
        inserts = [
            c for c in mock_db.execute.call_args_list
            if c.args and "INSERT INTO keywords" in str(c.args[0])
        ]
        for call in inserts:
            intent = call.args[1].get("intent")
            assert intent is None or intent in _VALID_INTENTS, (
                f"intent must be one of {_VALID_INTENTS} or None, got {intent!r}"
            )

    async def test_keyword_insert_volume_is_int_or_none(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            await KeywordResearchAgent().run(ctx)
        inserts = [
            c for c in mock_db.execute.call_args_list
            if c.args and "INSERT INTO keywords" in str(c.args[0])
        ]
        for call in inserts:
            vol = call.args[1].get("volume")
            assert vol is None or isinstance(vol, int), (
                f"volume must be int or None, got {type(vol).__name__}: {vol!r}"
            )

    async def test_keyword_insert_kd_is_float_or_none(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            await KeywordResearchAgent().run(ctx)
        inserts = [
            c for c in mock_db.execute.call_args_list
            if c.args and "INSERT INTO keywords" in str(c.args[0])
        ]
        for call in inserts:
            kd = call.args[1].get("kd")
            assert kd is None or isinstance(kd, float), (
                f"kd must be float or None, got {type(kd).__name__}: {kd!r}"
            )

    async def test_keyword_insert_cpc_is_float_or_none(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            await KeywordResearchAgent().run(ctx)
        inserts = [
            c for c in mock_db.execute.call_args_list
            if c.args and "INSERT INTO keywords" in str(c.args[0])
        ]
        for call in inserts:
            cpc = call.args[1].get("cpc")
            assert cpc is None or isinstance(cpc, float), (
                f"cpc must be float or None, got {type(cpc).__name__}: {cpc!r}"
            )

    # ── Failure modes ─────────────────────────────────────────────────────────

    async def test_failed_status_on_missing_prompt(self, mock_db, mock_llm) -> None:
        ctx = _make_ctx(mock_db, mock_llm)
        with patch.object(
            PromptRegistry, "get",
            AsyncMock(side_effect=PromptNotFoundError("keyword_research")),
        ):
            result = await KeywordResearchAgent().run(ctx)
        assert result.status == "failed"
        assert result.error is not None and len(result.error) > 5

    async def test_empty_llm_response_returns_zero_keywords(self, mock_db, mock_llm) -> None:
        mock_llm.complete = AsyncMock(return_value="")
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            result = await KeywordResearchAgent().run(ctx)
        assert result.status == "success"
        assert result.data["keywords_found"] == 0

    async def test_llm_refusal_returns_zero_keywords(self, mock_db, mock_llm) -> None:
        mock_llm.complete = AsyncMock(return_value="I cannot generate keywords for that topic.")
        ctx = _make_ctx(mock_db, mock_llm)
        with _patch_prompt():
            result = await KeywordResearchAgent().run(ctx)
        assert result.status == "success"
        assert result.data["keywords_found"] == 0


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.70

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"seed_keyword": "content marketing automation"},
    {"seed_keyword": "B2B SaaS SEO strategy"},
    {"seed_keyword": "email marketing best practices"},
]

RELEVANCE_JUDGE_CRITERIA: str = """
Score the keyword research output on these four dimensions (0.25 each):

1. Relevance (0–0.25): Are all keywords clearly topically related to the seed?
   Penalise: unrelated keywords, keywords from different domains.

2. Diversity (0–0.25): Do keywords span different subtopics, intents, or angles?
   Penalise: near-duplicate keywords, only one intent type.

3. Metric plausibility (0–0.25): Are volume (100–500k), kd (0–100), cpc (0–50) in range?
   Penalise: zero volumes on all, extreme values, missing metrics on most keywords.

4. Volume (0–0.25): Are there at least 5 distinct keyword ideas returned?
   Penalise: fewer than 5 keywords.

Sum the four dimensions for the final score.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="High-volume commercial seed",
        input_params={"seed_keyword": "best CRM software"},
        expected_fields={
            "keywords_found_min": 5,
            "has_commercial_intent": True,
            "keywords_mention_crm_or_software": True,
            "volume_range": (100, 500_000),
        },
        notes="All keywords should relate to CRM tools. Expect commercial + informational mix.",
    ),
    GroundTruthSample(
        description="Informational long-tail seed",
        input_params={"seed_keyword": "how to improve email open rates"},
        expected_fields={
            "keywords_found_min": 5,
            "has_informational_intent": True,
            "keywords_mention_email": True,
        },
        notes="Mostly informational intent expected. Should include how-to phrasing.",
    ),
    GroundTruthSample(
        description="Technical B2B seed",
        input_params={"seed_keyword": "marketing automation platform comparison"},
        expected_fields={
            "keywords_found_min": 5,
            "has_commercial_intent": True,
            "includes_comparison_variants": True,
        },
        notes="Should yield competitor and feature-comparison keywords.",
    ),
    GroundTruthSample(
        description="Low-volume niche seed",
        input_params={"seed_keyword": "account based marketing tactics B2B"},
        expected_fields={
            "keywords_found_min": 3,
            "all_keywords_relevant_to_abm": True,
        },
        notes="Niche topic — accept fewer keywords. Quality > quantity.",
    ),
    GroundTruthSample(
        description="Transactional seed",
        input_params={"seed_keyword": "buy marketing software online"},
        expected_fields={
            "keywords_found_min": 5,
            "has_transactional_or_commercial_intent": True,
            "no_irrelevant_categories": True,
        },
        notes="Should focus on purchase-intent keywords. No unrelated categories.",
    ),
]
