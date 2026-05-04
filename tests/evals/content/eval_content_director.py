"""
Evals for content_director agent.

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

AGENT_NAME: str = "content_director"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"opportunity_id": str}
#   Output: {"dispatched_formats": [str], "content_items_created": int}
#   DB:     INSERT INTO content_items for each dispatched format
#           agent_runs row with status='success'
#
# Field constraints:
#   dispatched_formats   list[str]   each in {'article','linkedin','twitter','newsletter'}
#   content_items_created int        == len(dispatched_formats)
#   all inserted content_items have status='draft'

_VALID_FORMATS = {"article", "linkedin", "twitter", "newsletter", "video_script", "lead_magnet"}


@pytest.mark.skip(reason="content_director not built yet")
class TestStructural_content_director:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_dispatched_formats_is_list(self, mock_db, mock_llm) -> None: ...
    async def test_dispatched_formats_are_valid_enum_values(self, mock_db, mock_llm) -> None: ...
    async def test_content_items_created_matches_dispatched_count(self, mock_db, mock_llm) -> None: ...
    async def test_at_least_one_format_dispatched(self, mock_db, mock_llm) -> None: ...
    async def test_inserted_content_items_have_status_draft(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...
    async def test_missing_opportunity_id_returns_failed(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.70

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"opportunity_id": ""},
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate content director dispatch decisions:
1. Format selection (0–0.40): Are the chosen formats appropriate for the opportunity's keyword intent?
   Example: a high-volume informational keyword should get an article + social posts.
   Penalise: dispatching video for a keyword with no video intent signals.
2. Coverage (0–0.30): Does the dispatch cover at least 2 formats for a standard opportunity?
   Penalise: only one format dispatched for a high-priority opportunity.
3. Consistency (0–0.30): Are all dispatched formats coherent with each other (same keyword focus)?
   Penalise: mismatched keywords or angles across formats.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="High-priority commercial opportunity",
        input_params={"opportunity_id": ""},
        expected_fields={"dispatched_formats_includes": ["article", "linkedin"], "count_gte": 2},
        notes="Should dispatch at minimum article + LinkedIn for a commercial opportunity.",
    ),
    GroundTruthSample(
        description="Informational opportunity (how-to keyword)",
        input_params={"opportunity_id": ""},
        expected_fields={"article_dispatched": True},
        notes="Informational keywords primarily warrant article creation.",
    ),
    GroundTruthSample(
        description="Trending topic opportunity",
        input_params={"opportunity_id": ""},
        expected_fields={"twitter_or_linkedin_dispatched": True},
        notes="Trend-driven content should include social media formats.",
    ),
    GroundTruthSample(
        description="Low-score opportunity (below threshold)",
        input_params={"opportunity_id": ""},
        expected_fields={"dispatched_formats_count_lte": 1},
        notes="Low-score opportunities should receive minimal investment (≤1 format).",
    ),
    GroundTruthSample(
        description="Newsletter-suitable opportunity (recurring topic)",
        input_params={"opportunity_id": ""},
        expected_fields={"newsletter_dispatched": True},
        notes="Evergreen topic — should trigger newsletter format.",
    ),
]
