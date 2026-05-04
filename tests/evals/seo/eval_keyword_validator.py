"""
Evals for keyword_validator agent.

SECTION 1 — STRUCTURAL EVAL  (automated, CI)      — skipped until agent is built
SECTION 2 — RELEVANCE EVAL   (automated, weekly)
SECTION 3 — GROUND TRUTH     (manual, monthly)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "apps" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from base import GroundTruthSample

AGENT_NAME: str = "keyword_validator"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"batch_size": int}  — process next N raw keywords for this org
#   Output: {"validated_count": int, "rejected_count": int}
#   DB:     UPDATE keywords SET status = 'validated' | 'archived' WHERE id IN (...)
#           agent_runs row with status='success'

@pytest.mark.skip(reason="keyword_validator not built yet")
class TestStructural_keyword_validator:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None:
        from agents.seo.keyword_validator import KeywordValidatorAgent
        ...

    async def test_validated_count_is_non_negative_int(self, mock_db, mock_llm) -> None: ...
    async def test_rejected_count_is_non_negative_int(self, mock_db, mock_llm) -> None: ...
    async def test_counts_sum_to_batch_size(self, mock_db, mock_llm) -> None: ...
    async def test_keyword_status_updated_to_validated_or_archived(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...
    async def test_empty_batch_returns_zero_counts(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.75

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"batch_size": 20},
    {"batch_size": 50},
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate keyword validation output quality:
1. Accuracy (0–0.4): Are validated keywords genuinely search-worthy?
   Penalise: nonsense keywords marked validated, good keywords marked archived.
2. Discrimination (0–0.3): Does the agent differentiate high vs low quality?
   Penalise: all-validated or all-rejected output (no real filtering).
3. Rationale (0–0.3): Are rejection reasons meaningful (if provided)?
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="Batch with obvious junk keywords",
        input_params={"batch_size": 20},
        expected_fields={
            "junk_keywords_rejected": True,
            "good_keywords_validated": True,
            "rejected_count_gte": 3,
        },
        notes="Should reject nonsense, overly broad (e.g. 'marketing'), or zero-volume keywords.",
    ),
    GroundTruthSample(
        description="Batch of high-quality niche keywords",
        input_params={"batch_size": 20},
        expected_fields={"validated_count_gte": 15},
        notes="Most keywords in this batch should pass validation.",
    ),
    GroundTruthSample(
        description="Empty batch (no raw keywords left)",
        input_params={"batch_size": 50},
        expected_fields={"validated_count": 0, "rejected_count": 0},
        notes="Agent should handle empty batch gracefully.",
    ),
    GroundTruthSample(
        description="Mixed quality batch",
        input_params={"batch_size": 30},
        expected_fields={"has_both_validated_and_rejected": True},
        notes="Realistic mix — expect both outcomes present.",
    ),
    GroundTruthSample(
        description="Batch with duplicate keywords",
        input_params={"batch_size": 20},
        expected_fields={"duplicates_not_double_counted": True},
        notes="Duplicate keywords should be deduplicated before validation.",
    ),
]
