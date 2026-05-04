"""
Evals for rag_searcher agent.

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

AGENT_NAME: str = "rag_searcher"
IS_BUILT: bool = False

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STRUCTURAL EVAL
# ══════════════════════════════════════════════════════════════════════════════
# Expected contract when built:
#   Input:  {"query": str, "top_k": int}  (default top_k=5)
#   Output: {"chunks_found": int, "results": [{"chunk_text": str, "score": float, "source_doc": str}]}
#   DB:     READ ONLY — no writes (vector similarity search on knowledge_chunks)
#           agent_runs row with status='success'
#
# Field constraints:
#   chunks_found          int    >= 0
#   results               list   len == min(top_k, chunks_found)
#   result.score          float  0.0–1.0 (cosine similarity or equivalent)
#   result.chunk_text     str    non-empty
#   result.source_doc     str    non-empty

@pytest.mark.skip(reason="rag_searcher not built yet")
class TestStructural_rag_searcher:

    async def test_status_is_valid_enum(self, mock_db, mock_llm) -> None: ...
    async def test_chunks_found_is_non_negative_int(self, mock_db, mock_llm) -> None: ...
    async def test_results_is_list(self, mock_db, mock_llm) -> None: ...
    async def test_result_count_bounded_by_top_k(self, mock_db, mock_llm) -> None: ...
    async def test_each_result_has_chunk_text(self, mock_db, mock_llm) -> None: ...
    async def test_each_result_score_is_float_0_to_1(self, mock_db, mock_llm) -> None: ...
    async def test_each_result_has_source_doc(self, mock_db, mock_llm) -> None: ...
    async def test_no_db_inserts_performed(self, mock_db, mock_llm) -> None: ...
    async def test_empty_knowledge_base_returns_zero_results(self, mock_db, mock_llm) -> None: ...
    async def test_agent_run_record_inserted(self, mock_db, mock_llm) -> None: ...


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — RELEVANCE EVAL
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_THRESHOLD: float = 0.72

RELEVANCE_SAMPLE_INPUTS: list[dict] = [
    {"query": "content marketing strategy examples", "top_k": 5},
    {"query": "email open rate benchmarks", "top_k": 3},
]

RELEVANCE_JUDGE_CRITERIA: str = """
Evaluate RAG search result quality:
1. Topical match (0–0.40): Are returned chunks genuinely about the query topic?
   Penalise: off-topic chunks with high scores, relevant chunks with low scores.
2. Score ordering (0–0.30): Are higher-scored chunks more relevant than lower-scored ones?
   Penalise: inverted ranking, all identical scores.
3. Source diversity (0–0.30): Do results come from multiple source documents (where available)?
   Penalise: all results from one document when knowledge base has multiple relevant sources.
"""


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — GROUND TRUTH SPOT CHECK
# ══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH_SAMPLES: list[GroundTruthSample] = [
    GroundTruthSample(
        description="Query matching a known ingested document",
        input_params={"query": "how to write a content brief", "top_k": 5},
        expected_fields={"chunks_found_gte": 1, "top_result_score_gte": 0.7},
        notes="Pre-ingest a document about content briefs. Top result should score >= 0.7.",
    ),
    GroundTruthSample(
        description="Query with no matching content in knowledge base",
        input_params={"query": "quantum computing applications", "top_k": 5},
        expected_fields={"chunks_found": 0},
        notes="Knowledge base has no quantum computing content — expect zero results.",
    ),
    GroundTruthSample(
        description="Broad query — top_k=10",
        input_params={"query": "marketing", "top_k": 10},
        expected_fields={"results_count_gte": 5, "results_count_lte": 10},
        notes="Broad query should return up to top_k results.",
    ),
    GroundTruthSample(
        description="Query with typos",
        input_params={"query": "conent mrketing stratgy", "top_k": 3},
        expected_fields={"chunks_found_gte": 0},
        notes="Typos — embedding search should still find relevant results if embeddings are robust.",
    ),
    GroundTruthSample(
        description="Exact phrase from an ingested document",
        input_params={"query": "", "top_k": 3},
        expected_fields={"top_result_score_gte": 0.9},
        notes="Paste an exact phrase from a known ingested doc. Should score very high.",
    ),
]
