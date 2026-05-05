"""Unit tests for RagSearcherAgent."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.knowledge.rag_searcher  # noqa: F401

from agents.knowledge.rag_searcher import RagSearcherAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

# Fake 1536-dim embedding (all zeros — valid shape, won't cause errors)
_FAKE_EMBEDDING: list[float] = [0.0] * 1536

# Three dummy knowledge_chunks rows: (id, chunk_text, source_doc, score)
_CHUNK_ROWS = [
    (str(uuid.uuid4()), "AI marketing automates repetitive tasks.", "blog/ai-marketing.md", 0.92),
    (str(uuid.uuid4()), "SEO automation reduces manual keyword work.", "blog/seo-guide.md", 0.87),
    (str(uuid.uuid4()), "Content strategy drives organic traffic growth.", "docs/strategy.md", 0.74),
]


def _chunk_row(chunk_id: str, text: str, source: str, score: float) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, i: (chunk_id, text, source, score)[i]
    return row


def _make_db(rows=None) -> AsyncMock:
    chunk_rows = [_chunk_row(*r) for r in (_CHUNK_ROWS if rows is None else rows)]

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "knowledge_chunks" in sql:
            result.fetchall.return_value = chunk_rows
        else:
            result.fetchall.return_value = []
            result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params={"query": "ai marketing automation", **(params or {})},
        config={},
        db=db,
        llm=MagicMock(),
    )


def _patch_embed(embedding: list[float] | None = None):
    vec = embedding if embedding is not None else _FAKE_EMBEDDING
    return patch(
        "agents.knowledge.rag_searcher.EmbeddingGenerator",
        **{"return_value.generate_one": AsyncMock(return_value=vec)},
    )


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_successful_run_returns_success_status() -> None:
    db = _make_db()
    with _patch_embed():
        result = await RagSearcherAgent().run(_ctx(db))
    assert result.status == "success"


async def test_returns_correct_chunk_count() -> None:
    db = _make_db()
    with _patch_embed():
        result = await RagSearcherAgent().run(_ctx(db))
    assert result.data["total_found"] == 3
    assert len(result.data["chunks"]) == 3


async def test_query_echoed_in_result() -> None:
    db = _make_db()
    with _patch_embed():
        result = await RagSearcherAgent().run(_ctx(db))
    assert result.data["query"] == "ai marketing automation"


async def test_chunk_fields_present() -> None:
    db = _make_db()
    with _patch_embed():
        result = await RagSearcherAgent().run(_ctx(db))
    chunk = result.data["chunks"][0]
    assert "chunk_id" in chunk
    assert "content" in chunk
    assert "source" in chunk
    assert "similarity_score" in chunk


async def test_chunks_ordered_by_score_descending() -> None:
    db = _make_db()
    with _patch_embed():
        result = await RagSearcherAgent().run(_ctx(db))
    scores = [c["similarity_score"] for c in result.data["chunks"]]
    assert scores == sorted(scores, reverse=True)


async def test_top_k_param_passed_to_db() -> None:
    db = _make_db()
    with _patch_embed():
        await RagSearcherAgent().run(_ctx(db, params={"query": "test", "top_k": 2}))
    search_calls = [
        c for c in db.execute.call_args_list
        if "knowledge_chunks" in str(c[0][0])
    ]
    assert search_calls[0][0][1]["top_k"] == 2


async def test_embedding_vector_passed_as_string_to_db() -> None:
    db = _make_db()
    with _patch_embed():
        await RagSearcherAgent().run(_ctx(db))
    search_calls = [
        c for c in db.execute.call_args_list
        if "knowledge_chunks" in str(c[0][0])
    ]
    vec_param = search_calls[0][0][1]["query_vec"]
    assert vec_param.startswith("[")
    assert vec_param.endswith("]")


async def test_sql_uses_cast_not_double_colon() -> None:
    """asyncpg named-param parser breaks on ::vector — must use CAST(...)."""
    db = _make_db()
    with _patch_embed():
        await RagSearcherAgent().run(_ctx(db))
    search_calls = [
        c for c in db.execute.call_args_list
        if "knowledge_chunks" in str(c[0][0])
    ]
    sql = str(search_calls[0][0][0])
    assert "CAST(:query_vec AS vector)" in sql
    assert "::vector" not in sql


async def test_tokens_zero_no_llm() -> None:
    db = _make_db()
    with _patch_embed():
        result = await RagSearcherAgent().run(_ctx(db))
    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


# ── Empty results ─────────────────────────────────────────────────────────────

async def test_empty_knowledge_base_returns_success() -> None:
    db = _make_db(rows=[])
    with _patch_embed():
        result = await RagSearcherAgent().run(_ctx(db))
    assert result.status == "success"
    assert result.data["total_found"] == 0
    assert result.data["chunks"] == []


# ── Embedding failure → graceful degradation ──────────────────────────────────

async def test_embedding_failure_returns_no_embedding_api_status() -> None:
    db = _make_db()
    with patch(
        "agents.knowledge.rag_searcher.EmbeddingGenerator",
        **{"return_value.generate_one": AsyncMock(side_effect=Exception("No API key"))},
    ):
        result = await RagSearcherAgent().run(_ctx(db))
    assert result.status == "no_embedding_api"
    assert result.data["chunks"] == []
    assert result.data["total_found"] == 0


async def test_embedding_failure_no_db_query() -> None:
    """If embedding fails, we must not query the DB for vectors."""
    db = _make_db()
    with patch(
        "agents.knowledge.rag_searcher.EmbeddingGenerator",
        **{"return_value.generate_one": AsyncMock(side_effect=Exception("timeout"))},
    ):
        await RagSearcherAgent().run(_ctx(db))
    search_calls = [
        c for c in db.execute.call_args_list
        if "knowledge_chunks" in str(c[0][0])
    ]
    assert len(search_calls) == 0


async def test_embedding_failure_error_message_descriptive() -> None:
    db = _make_db()
    with patch(
        "agents.knowledge.rag_searcher.EmbeddingGenerator",
        **{"return_value.generate_one": AsyncMock(side_effect=Exception("No API key"))},
    ):
        result = await RagSearcherAgent().run(_ctx(db))
    assert result.error is not None
    assert len(result.error) > 10


# ── Missing query param ───────────────────────────────────────────────────────

async def test_missing_query_returns_failed() -> None:
    db = _make_db()
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={}, config={}, db=db, llm=MagicMock()
    )
    result = await RagSearcherAgent().run(ctx)
    assert result.status == "failed"
    assert "query" in (result.error or "")
