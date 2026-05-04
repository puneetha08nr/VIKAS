"""
Evals for rank_tracker agent.

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

AGENT_NAME: str = "rank_tracker"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"keyword_ids": [str, ...]} or {"all": true}
#   Output: {"tracked_count": int, "not_found_count": int}
#   DB:     UPDATE keywords SET rank, rank_updated_at
#           or INSERT INTO rank_history (keyword_id, rank, tracked_at)
#
# Field constraints:
#   rank   int | None   1–1000 (None if not ranking)

@pytest.mark.skip(reason="rank_tracker not built yet")
class TestStructural_rank_tracker:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_tracked_count_is_non_negative_int(self, mock_db, mock_llm) -> None: ...
    async def test_not_found_count_is_non_negative_int(self, mock_db, mock_llm) -> None: ...
    async def test_rank_is_int_or_none(self, mock_db, mock_llm) -> None: ...
    async def test_rank_within_valid_range(self, mock_db, mock_llm) -> None: ...
    async def test_db_write_per_tracked_keyword(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...
    async def test_empty_keyword_list_returns_zero_tracked(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.65

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"keyword_ids": []},
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate rank tracking output quality:
1. Completeness (0–0.5): Were all provided keywords tracked (tracked_count == input count)?
   Penalise: low tracked_count relative to input size.
2. Rank plausibility (0–0.5): Are returned ranks in 1–1000 range or None?
   Penalise: rank values outside 1–1000, non-null ranks of 0.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="Keywords the site ranks for",
        input_params={"keyword_ids": []},
        expected_fields={"tracked_count_gte": 1, "some_ranks_between_1_and_100": True},
        notes="Pre-populate with keywords the test site already ranks for.",
    ),
    GroundTruthSample(
        description="Keywords the site does not rank for",
        input_params={"keyword_ids": []},
        expected_fields={"not_found_count_gte": 1},
        notes="Use brand-new keywords with no existing ranking.",
    ),
    GroundTruthSample(
        description="Single keyword tracking",
        input_params={"keyword_ids": []},
        expected_fields={"tracked_count_in": [0, 1]},
        notes="Simple single-keyword check.",
    ),
    GroundTruthSample(
        description="Large batch (50+ keywords)",
        input_params={"all": True},
        expected_fields={"tracked_count_gte": 10},
        notes="Batch tracking all validated keywords.",
    ),
    GroundTruthSample(
        description="Empty keyword list",
        input_params={"keyword_ids": []},
        expected_fields={"tracked_count": 0, "not_found_count": 0},
        notes="Agent should handle empty list gracefully.",
    ),
]
