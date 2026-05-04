"""
Evals for document_ingester agent.

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

AGENT_NAME: str = "document_ingester"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"document_url": str, "document_type": "pdf|url|text"}
#   Output: {"chunks_created": int, "doc_id": str}
#   DB:     INSERT INTO knowledge_chunks (chunk_text, embedding vector, source_doc, org_id)
#           agent_runs row with status='success'
#
# Field constraints:
#   chunks_created         int   >= 1
#   doc_id                 str   non-empty
#   knowledge_chunks.embedding  vector(1536)  not null
#   knowledge_chunks.chunk_text str           non-empty, len >= 50 chars

@pytest.mark.skip(reason="document_ingester not built yet")
class TestStructural_document_ingester:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_chunks_created_is_positive_int(self, mock_db, mock_llm) -> None: ...
    async def test_doc_id_is_non_empty_string(self, mock_db, mock_llm) -> None: ...
    async def test_knowledge_chunk_rows_inserted(self, mock_db, mock_llm) -> None: ...
    async def test_chunk_text_is_non_empty(self, mock_db, mock_llm) -> None: ...
    async def test_embedding_vector_has_correct_dimension(self, mock_db, mock_llm) -> None: ...
    async def test_source_doc_set_in_chunk(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...
    async def test_invalid_url_returns_failed(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.65

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"document_url": "https://example.com/sample-blog-post", "document_type": "url"},
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate document ingestion output quality:
1. Chunk completeness (0–0.40): Do chunks collectively cover the full document?
   Penalise: fewer chunks than expected for document length, large gaps in content.
2. Chunk coherence (0–0.30): Is each chunk a self-contained, meaningful passage?
   Penalise: chunks split mid-sentence, chunks of only 1-2 sentences.
3. Metadata accuracy (0–0.30): Does source_doc correctly reference the input document?
   Penalise: missing source_doc, incorrect URL/filename stored.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="Short blog post (< 1000 words)",
        input_params={"document_url": "", "document_type": "url"},
        expected_fields={"chunks_created_in": [2, 6], "no_empty_chunks": True},
        notes="Short document — expect 2-6 chunks.",
    ),
    GroundTruthSample(
        description="Long PDF whitepaper (10+ pages)",
        input_params={"document_url": "", "document_type": "pdf"},
        expected_fields={"chunks_created_gte": 10, "sections_preserved": True},
        notes="Multi-page document — section headings should anchor chunk boundaries.",
    ),
    GroundTruthSample(
        description="Plain text input",
        input_params={"document_type": "text", "document_text": "Sample marketing content..."},
        expected_fields={"chunks_created_gte": 1},
        notes="Direct text input — should work without URL fetching.",
    ),
    GroundTruthSample(
        description="Duplicate document re-ingestion",
        input_params={"document_url": "", "document_type": "url"},
        expected_fields={"no_duplicate_chunks": True},
        notes="Re-ingesting same document should not create duplicate chunks.",
    ),
    GroundTruthSample(
        description="Invalid or inaccessible URL",
        input_params={"document_url": "https://this-url-does-not-exist.test/404", "document_type": "url"},
        expected_fields={"status": "failed", "error_message_present": True},
        notes="Should fail gracefully with a meaningful error message.",
    ),
]
