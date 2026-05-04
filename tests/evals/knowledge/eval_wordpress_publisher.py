"""
Evals for wordpress_publisher agent.

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

AGENT_NAME: str = "wordpress_publisher"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"content_item_id": str}  — must have status='approved'
#   Output: {"published_url": str, "post_id": str | int}
#   DB:     UPDATE content_items SET status='published', published_url=<url>
#           agent_runs row with status='success'
#
# Guard: must NOT publish if content_items.status != 'approved'
#
# Field constraints:
#   published_url   str  starts with 'http', non-empty
#   post_id         str | int  non-empty / non-zero

@pytest.mark.skip(reason="wordpress_publisher not built yet")
class TestStructural_wordpress_publisher:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_published_url_starts_with_http(self, mock_db, mock_llm) -> None: ...
    async def test_post_id_is_non_empty(self, mock_db, mock_llm) -> None: ...
    async def test_content_item_status_updated_to_published(self, mock_db, mock_llm) -> None: ...
    async def test_published_url_stored_in_db(self, mock_db, mock_llm) -> None: ...
    async def test_refuses_to_publish_unapproved_content(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...
    async def test_wp_api_failure_returns_failed_status(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.80

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"content_item_id": ""},
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate WordPress publishing result quality:
1. Publication success (0–0.50): Is the returned published_url accessible and correct?
   Penalise: URL that 404s, URL pointing to wrong domain, empty URL.
2. Metadata fidelity (0–0.30): Does the published post match title, body, and tags from content_items?
   Penalise: truncated body, wrong title, missing tags.
3. Status accuracy (0–0.20): Is content_items.status correctly updated to 'published'?
   Penalise: status still 'approved' after publish, or updated to wrong value.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ═════════════════════════════════════════���════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="Publish approved article to staging WP site",
        input_params={"content_item_id": ""},
        expected_fields={"published_url_accessible": True, "status_is_published": True},
        notes="Visit the returned URL manually to confirm the post is live.",
    ),
    GroundTruthSample(
        description="Attempt to publish unapproved content (should fail)",
        input_params={"content_item_id": ""},
        expected_fields={"status": "failed", "error_mentions_approval": True},
        notes="Use a content_item with status='draft'. Agent must refuse to publish.",
    ),
    GroundTruthSample(
        description="Article with images in body",
        input_params={"content_item_id": ""},
        expected_fields={"images_uploaded_to_wp": True, "img_urls_in_published_post": True},
        notes="Image URLs in body should be re-hosted on WP media library.",
    ),
    GroundTruthSample(
        description="Article with SEO meta (title, description)",
        input_params={"content_item_id": ""},
        expected_fields={"seo_title_set": True, "meta_description_set": True},
        notes="Check WP post meta for Yoast/RankMath SEO fields.",
    ),
    GroundTruthSample(
        description="Re-publish (update existing post)",
        input_params={"content_item_id": ""},
        expected_fields={"post_updated_not_duplicated": True},
        notes="If post_id already exists in WP, agent should UPDATE, not INSERT.",
    ),
]
