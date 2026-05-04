"""
Evals for gap_analyzer agent.

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

AGENT_NAME: str = "gap_analyzer"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"keyword_ids": [str, ...]}  — list of validated keyword UUIDs
#   Output: {"opportunities_found": int}
#   DB:     INSERT INTO opportunities (keyword_id, source, composite_score, status, ...)
#           agent_runs row with status='success'
#
# Field constraints:
#   opportunities.composite_score  float  0.0–1.0
#   opportunities.status           str    in {"pending", "scored", "dismissed"}
#   opportunities.source           str    non-empty

@pytest.mark.skip(reason="gap_analyzer not built yet")
class TestStructural_gap_analyzer:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_opportunities_found_is_non_negative_int(self, mock_db, mock_llm) -> None: ...
    async def test_opportunity_row_inserted(self, mock_db, mock_llm) -> None: ...
    async def test_composite_score_is_float_0_to_1(self, mock_db, mock_llm) -> None: ...
    async def test_opportunity_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_keyword_id_fk_present_in_insert(self, mock_db, mock_llm) -> None: ...
    async def test_empty_keyword_list_returns_zero_opportunities(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.70

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"keyword_ids": []},   # runner will populate with real IDs at eval time
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate gap analysis output quality:
1. Score distribution (0–0.35): Do composite scores spread meaningfully (not all 0.5)?
   Penalise: all identical scores, scores outside 0–1.
2. Prioritisation (0–0.35): Are high-score opportunities genuinely attractive?
   Penalise: high scores for low-volume or high-difficulty keywords.
3. Coverage (0–0.30): Are there enough opportunities surfaced (at least 3)?
   Penalise: fewer than 3 opportunities from a batch of 10+ keywords.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="High-opportunity keyword set",
        input_params={"keyword_ids": []},
        expected_fields={"opportunities_found_min": 3, "top_score_gte": 0.7},
        notes="Keywords with low kd and high volume — should yield several opportunities.",
    ),
    GroundTruthSample(
        description="Low-opportunity keyword set (high competition)",
        input_params={"keyword_ids": []},
        expected_fields={"opportunities_found_max": 2, "scores_below": 0.5},
        notes="Highly competitive keywords — should surface few or low-scored opportunities.",
    ),
    GroundTruthSample(
        description="Mixed quality keyword set",
        input_params={"keyword_ids": []},
        expected_fields={"has_score_spread": True},
        notes="Score variance > 0.2 expected across the batch.",
    ),
    GroundTruthSample(
        description="Single keyword input",
        input_params={"keyword_ids": []},
        expected_fields={"opportunities_found_in": [0, 1]},
        notes="Single keyword may or may not qualify as an opportunity.",
    ),
    GroundTruthSample(
        description="Empty keyword list",
        input_params={"keyword_ids": []},
        expected_fields={"opportunities_found": 0},
        notes="Empty input — no opportunities should be created.",
    ),
]
