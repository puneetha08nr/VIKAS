"""
Evals for brand_voice_keeper agent.

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

AGENT_NAME: str = "brand_voice_keeper"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"approved_content_ids": [str]}  — IDs of human-approved content items
#   Output: {"brand_voice_id": str, "patterns_extracted": int}
#   DB:     UPSERT INTO brand_voice (tone, vocabulary, banned_phrases, style_rules_jsonb)
#           agent_runs row with status='success'
#
# Field constraints:
#   brand_voice.tone             str   non-empty
#   brand_voice.vocabulary       str | None
#   brand_voice.banned_phrases   str | None
#   brand_voice.style_rules      dict | None  (JSONB)
#   patterns_extracted           int  >= 0

@pytest.mark.skip(reason="brand_voice_keeper not built yet")
class TestStructural_brand_voice_keeper:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_brand_voice_id_is_non_empty_string(self, mock_db, mock_llm) -> None: ...
    async def test_patterns_extracted_is_non_negative_int(self, mock_db, mock_llm) -> None: ...
    async def test_brand_voice_upserted_in_db(self, mock_db, mock_llm) -> None: ...
    async def test_tone_is_non_empty_string(self, mock_db, mock_llm) -> None: ...
    async def test_empty_approved_content_does_not_crash(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.68

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"approved_content_ids": []},
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate extracted brand voice quality:
1. Tone specificity (0–0.35): Is the extracted tone more specific than generic adjectives?
   Example of good: "authoritative but approachable, data-first, avoids jargon"
   Penalise: single-word tone like "professional" with no elaboration.
2. Banned phrases relevance (0–0.35): Are banned phrases genuinely problematic clichés
   for the content type? Penalise: banning common words, empty banned list from real content.
3. Style rule usefulness (0–0.30): Do style rules give actionable guidance to future writers?
   Penalise: vague rules like "write well", missing sentence-level guidance.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="Extract from 5 approved blog articles",
        input_params={"approved_content_ids": []},
        expected_fields={"tone_is_specific": True, "banned_phrases_count_gte": 3},
        notes="Should extract consistent tone and identify overused clichés.",
    ),
    GroundTruthSample(
        description="Extract from 2 approved LinkedIn posts",
        input_params={"approved_content_ids": []},
        expected_fields={"tone_reflects_social_context": True},
        notes="Social content has different tone than articles — should be reflected.",
    ),
    GroundTruthSample(
        description="Re-extraction after new approvals (incremental update)",
        input_params={"approved_content_ids": []},
        expected_fields={"existing_rules_preserved": True, "new_patterns_added": True},
        notes="Subsequent runs should refine, not reset, brand voice rules.",
    ),
    GroundTruthSample(
        description="Empty approved content list (first run, no data)",
        input_params={"approved_content_ids": []},
        expected_fields={"patterns_extracted": 0, "status": "success"},
        notes="Should not crash — return empty voice with status success.",
    ),
    GroundTruthSample(
        description="Conflicting tone signals in approved content",
        input_params={"approved_content_ids": []},
        expected_fields={"tone_acknowledges_variation": True},
        notes="Some content is formal, some is casual — voice should reflect the range.",
    ),
]
