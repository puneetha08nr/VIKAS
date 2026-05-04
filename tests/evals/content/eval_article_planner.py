"""
Evals for article_planner agent.

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

AGENT_NAME: str = "article_planner"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"opportunity_id": str, "keyword": str}
#   Output: {"content_item_id": str (uuid), "section_count": int}
#   DB:     INSERT INTO content_items (format='article', status='draft', body=<outline>)
#           agent_runs row with status='success'
#
# Field constraints:
#   content_items.format    str  'article'
#   content_items.status    str  'draft'
#   content_items.title     str  non-empty
#   content_items.body      str  non-empty (outline JSON or markdown)
#   section_count           int  >= 3

@pytest.mark.skip(reason="article_planner not built yet")
class TestStructural_article_planner:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_content_item_id_is_valid_uuid_string(self, mock_db, mock_llm) -> None: ...
    async def test_section_count_is_int_gte_3(self, mock_db, mock_llm) -> None: ...
    async def test_content_item_inserted_with_format_article(self, mock_db, mock_llm) -> None: ...
    async def test_content_item_status_is_draft(self, mock_db, mock_llm) -> None: ...
    async def test_content_item_title_is_non_empty(self, mock_db, mock_llm) -> None: ...
    async def test_content_item_body_is_non_empty(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...
    async def test_missing_opportunity_id_returns_failed(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.72

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"opportunity_id": "", "keyword": "content marketing automation tools"},
    {"opportunity_id": "", "keyword": "how to build a B2B content strategy"},
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate article outline quality:
1. Keyword alignment (0–0.30): Does the outline directly address the target keyword?
   Penalise: outline that ignores the keyword or drifts to unrelated topics.
2. Structure (0–0.30): Are there 3–8 logical sections with a clear narrative arc?
   Penalise: fewer than 3 sections, disjointed sections, no intro or conclusion.
3. SEO intent (0–0.20): Does the outline match the keyword's search intent (info/commercial)?
   Penalise: commercial keyword getting only how-to sections.
4. Content depth signals (0–0.20): Do section headings promise substantive coverage?
   Penalise: vague headings like 'Introduction' with no supporting detail.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="Informational keyword — how-to article",
        input_params={"keyword": "how to create a content calendar"},
        expected_fields={
            "section_count_gte": 4,
            "first_section_is_intro_or_overview": True,
            "last_section_is_conclusion_or_cta": True,
        },
        notes="Expect step-by-step sections. Practical focus.",
    ),
    GroundTruthSample(
        description="Commercial keyword — comparison article",
        input_params={"keyword": "best marketing automation platforms 2024"},
        expected_fields={
            "section_count_gte": 5,
            "includes_comparison_section": True,
            "includes_recommendations": True,
        },
        notes="Should include side-by-side comparison and recommendations.",
    ),
    GroundTruthSample(
        description="Long-tail question keyword",
        input_params={"keyword": "what is account based marketing and how does it work"},
        expected_fields={"section_count_gte": 3, "answers_the_question": True},
        notes="Should directly answer the question in the first 2 sections.",
    ),
    GroundTruthSample(
        description="Short keyword with broad intent",
        input_params={"keyword": "content marketing"},
        expected_fields={"section_count_gte": 5, "covers_definition_and_strategy": True},
        notes="Broad keyword — should produce a comprehensive pillar article outline.",
    ),
    GroundTruthSample(
        description="Keyword with specific industry context",
        input_params={"keyword": "SaaS product-led growth content strategy"},
        expected_fields={"mentions_plg_or_saas": True, "section_count_gte": 4},
        notes="Outline should reflect the SaaS/PLG context, not generic content advice.",
    ),
]
