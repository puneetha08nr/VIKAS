"""
Evals for linkedin_agent.

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

AGENT_NAME: str = "linkedin_agent"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"keyword": str, "opportunity_id": str}
#   Output: {"content_item_id": str, "post_length": int, "has_hook": bool}
#   DB:     INSERT INTO content_items (format='linkedin', status='draft', body=<post text>)
#           agent_runs row with status='success'
#
# Field constraints:
#   content_items.format     str    'linkedin'
#   content_items.status     str    'draft'
#   content_items.body       str    non-empty, 150–3000 chars
#   post_length              int    150–3000
#   has_hook                 bool

_LINKEDIN_MIN_CHARS = 150
_LINKEDIN_MAX_CHARS = 3000


@pytest.mark.skip(reason="linkedin_agent not built yet")
class TestStructural_linkedin_agent:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_content_item_id_is_valid_uuid_string(self, mock_db, mock_llm) -> None: ...
    async def test_post_length_is_within_linkedin_limits(self, mock_db, mock_llm) -> None: ...
    async def test_has_hook_is_bool(self, mock_db, mock_llm) -> None: ...
    async def test_content_item_inserted_with_format_linkedin(self, mock_db, mock_llm) -> None: ...
    async def test_content_item_status_is_draft(self, mock_db, mock_llm) -> None: ...
    async def test_body_length_within_linkedin_limits(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.70

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"keyword": "B2B content marketing strategy", "opportunity_id": ""},
    {"keyword": "marketing automation ROI", "opportunity_id": ""},
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate LinkedIn post quality for a B2B marketing audience:
1. Hook strength (0–0.30): Does the first line stop the scroll?
   Penalise: generic openers like "In today's world...", questions that are too broad.
2. Keyword relevance (0–0.25): Does the post naturally incorporate the keyword topic?
   Penalise: post that barely mentions the core topic.
3. LinkedIn format (0–0.25): Does the post use LinkedIn conventions (short paragraphs,
   line breaks, appropriate emojis or hashtags at end)?
   Penalise: dense paragraphs, no line breaks, zero engagement hooks.
4. CTA presence (0–0.20): Does the post end with a clear call-to-action or question?
   Penalise: posts that end abruptly with no engagement invitation.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="Thought-leadership post on AI marketing",
        input_params={"keyword": "AI marketing automation"},
        expected_fields={"has_strong_hook": True, "post_length_gte": 300, "ends_with_cta": True},
        notes="Should read as a genuine opinion piece, not a product pitch.",
    ),
    GroundTruthSample(
        description="Data-driven post with stat",
        input_params={"keyword": "email marketing open rates"},
        expected_fields={"includes_statistic_or_number": True, "has_hook": True},
        notes="Best LinkedIn posts open with a surprising stat.",
    ),
    GroundTruthSample(
        description="Story-format post",
        input_params={"keyword": "content marketing results"},
        expected_fields={"narrative_structure": True, "personal_tone": True},
        notes="Should read like a personal experience story, not a blog excerpt.",
    ),
    GroundTruthSample(
        description="Short punchy post (< 500 chars)",
        input_params={"keyword": "marketing ROI"},
        expected_fields={"post_length_lte": 500, "high_impact_per_word": True},
        notes="Brevity test — every word should earn its place.",
    ),
    GroundTruthSample(
        description="Post respects brand voice (no banned phrases)",
        input_params={"keyword": "content strategy"},
        expected_fields={"no_banned_phrases": True, "tone_matches_brand": True},
        notes="Verify against brand_voice.banned_phrases and tone rules.",
    ),
]
