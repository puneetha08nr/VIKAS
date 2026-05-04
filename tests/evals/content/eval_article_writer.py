"""
Evals for article_writer agent.

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

AGENT_NAME: str = "article_writer"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"content_item_id": str}
#   Output: {"content_item_id": str, "word_count": int}
#   DB:     UPDATE content_items SET body=<full article>, word_count=int, seo_score=float
#           agent_runs row with status='success'
#
# Field constraints:
#   content_items.body       str   non-empty, len >= 500 words
#   content_items.word_count int   >= 500
#   content_items.seo_score  float 0.0–1.0 or None

@pytest.mark.skip(reason="article_writer not built yet")
class TestStructural_article_writer:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_content_item_id_echoed_in_result(self, mock_db, mock_llm) -> None: ...
    async def test_word_count_is_int_gte_500(self, mock_db, mock_llm) -> None: ...
    async def test_body_updated_in_db(self, mock_db, mock_llm) -> None: ...
    async def test_word_count_stored_in_db(self, mock_db, mock_llm) -> None: ...
    async def test_seo_score_is_float_or_none(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...
    async def test_missing_content_item_returns_failed(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.72

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"content_item_id": ""},   # runner populates with a real draft content_item_id
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate full article quality:
1. Keyword focus (0–0.25): Is the target keyword used naturally throughout?
   Penalise: keyword stuffing (>3% density), keyword never appears.
2. Depth (0–0.25): Does each section provide substantive content (>100 words/section)?
   Penalise: thin sections, padded filler, list-only content.
3. Coherence (0–0.25): Does the article flow logically from intro to conclusion?
   Penalise: abrupt topic switches, missing transitions, no conclusion.
4. Originality (0–0.25): Does the content add insight beyond restating the question?
   Penalise: generic platitudes, no concrete examples or data points.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="1500-word informational article",
        input_params={"content_item_id": ""},
        expected_fields={"word_count_gte": 1200, "has_intro_and_conclusion": True},
        notes="Full article — rate on coherence and depth above all.",
    ),
    GroundTruthSample(
        description="2000-word comparison article",
        input_params={"content_item_id": ""},
        expected_fields={"word_count_gte": 1800, "includes_comparison_table_or_list": True},
        notes="Should include structured comparison. Check for brand voice consistency.",
    ),
    GroundTruthSample(
        description="Article matches provided outline sections",
        input_params={"content_item_id": ""},
        expected_fields={"sections_match_outline": True},
        notes="Every section from the planner outline should appear in the final article.",
    ),
    GroundTruthSample(
        description="Article respects brand voice (tone, banned phrases)",
        input_params={"content_item_id": ""},
        expected_fields={"no_banned_phrases": True, "tone_matches_brand": True},
        notes="Check brand_voice table for banned phrases and tone rules.",
    ),
    GroundTruthSample(
        description="Article contains actionable takeaways",
        input_params={"content_item_id": ""},
        expected_fields={"has_actionable_tips": True, "reader_knows_next_step": True},
        notes="Reader should finish the article knowing what to do next.",
    ),
]
