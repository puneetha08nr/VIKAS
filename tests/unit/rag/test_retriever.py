import random
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.retriever import RAGRetriever
from rag.embeddings import EmbeddingGenerator


# ── Shared fixture: random 1536-dim embedding ─────────────────────────────────

@pytest.fixture
def random_vector() -> list[float]:
    rng = random.Random(42)
    return [rng.uniform(-1, 1) for _ in range(1536)]


@pytest.fixture
def mock_embeddings(random_vector: list[float]) -> MagicMock:
    gen = MagicMock(spec=EmbeddingGenerator)
    gen.generate_one = AsyncMock(return_value=random_vector)
    gen.generate = AsyncMock(return_value=[random_vector])
    return gen


@pytest.fixture
def retriever(mock_embeddings: MagicMock) -> RAGRetriever:
    return RAGRetriever(embeddings=mock_embeddings)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_db_rows(n: int) -> list[tuple]:
    return [
        (f"chunk text {i}", f"source_{i}.md", {"page": i}, round(0.9 - i * 0.05, 4))
        for i in range(n)
    ]


def _db_returning(rows: list[tuple]) -> AsyncMock:
    result = MagicMock()
    result.fetchall.return_value = rows
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


# ── Result format ─────────────────────────────────────────────────────────────

async def test_search_returns_list_of_dicts(
    retriever: RAGRetriever, random_vector: list[float]
) -> None:
    db = _db_returning(_make_db_rows(3))
    results = await retriever.search("test query", "org-1", db, top_k=3)

    assert isinstance(results, list)
    assert all(isinstance(r, dict) for r in results)


async def test_search_result_has_required_keys(
    retriever: RAGRetriever,
) -> None:
    db = _db_returning(_make_db_rows(1))
    results = await retriever.search("query", "org-1", db)

    assert set(results[0].keys()) == {"chunk_text", "source_doc", "metadata", "similarity"}


async def test_search_result_values_are_correct_types(
    retriever: RAGRetriever,
) -> None:
    db = _db_returning(_make_db_rows(2))
    results = await retriever.search("query", "org-1", db)

    for r in results:
        assert isinstance(r["chunk_text"], str)
        assert isinstance(r["source_doc"], str)
        assert isinstance(r["metadata"], dict)
        assert isinstance(r["similarity"], float)


async def test_search_returns_correct_number_of_results(
    retriever: RAGRetriever,
) -> None:
    db = _db_returning(_make_db_rows(5))
    results = await retriever.search("query", "org-1", db, top_k=5)
    assert len(results) == 5


async def test_search_empty_result_set(retriever: RAGRetriever) -> None:
    db = _db_returning([])
    results = await retriever.search("query", "org-1", db)
    assert results == []


# ── Embedding generation ──────────────────────────────────────────────────────

async def test_search_calls_generate_one_with_query(
    retriever: RAGRetriever, mock_embeddings: MagicMock
) -> None:
    db = _db_returning([])
    await retriever.search("my search query", "org-1", db)

    mock_embeddings.generate_one.assert_called_once_with("my search query")


async def test_search_passes_vector_to_db(
    retriever: RAGRetriever, random_vector: list[float]
) -> None:
    db = _db_returning([])
    await retriever.search("query", "org-1", db, top_k=7)

    db.execute.assert_called_once()
    _, params = db.execute.call_args[0]
    assert params["top_k"] == 7
    # Vector literal should contain the first element of our random vector
    assert str(random_vector[0])[:6] in params["vector"]


# ── SQL correctness ───────────────────────────────────────────────────────────

async def test_search_sql_references_rls_setting(
    retriever: RAGRetriever,
) -> None:
    db = _db_returning([])
    await retriever.search("query", "org-1", db)

    sql = str(db.execute.call_args[0][0])
    assert "current_setting" in sql
    assert "app.current_org_id" in sql


async def test_search_sql_uses_cosine_distance_operator(
    retriever: RAGRetriever,
) -> None:
    db = _db_returning([])
    await retriever.search("query", "org-1", db)

    sql = str(db.execute.call_args[0][0])
    assert "<=>" in sql


async def test_search_similarity_values_are_floats(retriever: RAGRetriever) -> None:
    rows = [("text", "doc.md", {}, "0.875")]  # DB might return string
    db = _db_returning(rows)
    results = await retriever.search("query", "org-1", db)

    assert isinstance(results[0]["similarity"], float)
    assert results[0]["similarity"] == pytest.approx(0.875)
