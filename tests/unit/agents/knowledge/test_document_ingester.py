"""Unit tests for DocumentIngesterAgent."""
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.knowledge.document_ingester  # noqa: F401

from agents.knowledge.document_ingester import DocumentIngesterAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"
_FAKE_EMBEDDING = [0.1] * 1536

_SAMPLE_CHUNKS = [
    {"text": "AI is transforming marketing.", "chunk_index": 0, "token_count": 6},
    {"text": "Automation drives efficiency.", "chunk_index": 1, "token_count": 4},
]


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params=params or {},
        config={},
        db=db,
        llm=MagicMock(),
    )


def _patch_chunker(chunks=None):
    c = chunks if chunks is not None else _SAMPLE_CHUNKS
    m = MagicMock()
    m.chunk.return_value = c
    return patch("agents.knowledge.document_ingester.TextChunker", return_value=m)


def _patch_embedder(vectors=None):
    v = vectors if vectors is not None else [_FAKE_EMBEDDING]
    m = MagicMock()
    m.generate = AsyncMock(return_value=v)
    return patch("agents.knowledge.document_ingester.EmbeddingGenerator", return_value=m)


def _patch_extract(text="Sample document content about AI marketing."):
    return patch(
        "agents.knowledge.document_ingester._extract_text",
        new=AsyncMock(return_value=text),
    )


# ── Validation ────────────────────────────────────────────────────────────────

class TestValidation:
    @pytest.mark.asyncio
    async def test_missing_file_path_returns_failed(self):
        db = _make_db()
        result = await DocumentIngesterAgent().run(_ctx(db, {}))
        assert result.status == "failed"
        assert "file_path" in result.error.lower()

    @pytest.mark.asyncio
    async def test_unsupported_extension_returns_failed(self):
        db = _make_db()
        params = {"file_path": "/tmp/doc.xlsx", "source_name": "doc"}
        with _patch_extract():
            result = await DocumentIngesterAgent().run(_ctx(db, params))
        assert result.status == "failed"
        assert "Unsupported" in result.error

    @pytest.mark.asyncio
    async def test_empty_text_returns_failed(self):
        db = _make_db()
        params = {"file_path": "/tmp/doc.txt"}
        with _patch_extract("   "), _patch_chunker([]):
            result = await DocumentIngesterAgent().run(_ctx(db, params))
        assert result.status == "failed"


# ── Happy path ────────────────────────────────────────────────────────────────

class TestHappyPath:
    @pytest.mark.asyncio
    async def test_success_status(self):
        db = _make_db()
        params = {"file_path": "/tmp/doc.txt", "source_name": "My Doc"}
        with _patch_extract(), _patch_chunker(), _patch_embedder():
            result = await DocumentIngesterAgent().run(_ctx(db, params))
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_chunks_created_count(self):
        db = _make_db()
        params = {"file_path": "/tmp/doc.pdf", "source_name": "Test"}
        with _patch_extract(), _patch_chunker(_SAMPLE_CHUNKS), _patch_embedder([_FAKE_EMBEDDING, _FAKE_EMBEDDING]):
            result = await DocumentIngesterAgent().run(_ctx(db, params))
        assert result.data["chunks_created"] == 2

    @pytest.mark.asyncio
    async def test_source_name_defaults_to_filename(self):
        db = _make_db()
        params = {"file_path": "/tmp/myfile.txt"}
        with _patch_extract(), _patch_chunker(), _patch_embedder():
            result = await DocumentIngesterAgent().run(_ctx(db, params))
        assert result.data["source_name"] == "myfile.txt"

    @pytest.mark.asyncio
    async def test_custom_source_name_used(self):
        db = _make_db()
        params = {"file_path": "/tmp/doc.txt", "source_name": "Brand Guide 2025"}
        with _patch_extract(), _patch_chunker(), _patch_embedder():
            result = await DocumentIngesterAgent().run(_ctx(db, params))
        assert result.data["source_name"] == "Brand Guide 2025"

    @pytest.mark.asyncio
    async def test_db_insert_called_per_chunk(self):
        db = _make_db()
        params = {"file_path": "/tmp/doc.docx", "source_name": "Test"}
        with _patch_extract(), _patch_chunker(_SAMPLE_CHUNKS), _patch_embedder([_FAKE_EMBEDDING, _FAKE_EMBEDDING]):
            await DocumentIngesterAgent().run(_ctx(db, params))
        inserts = [c for c in db.execute.call_args_list if "INSERT INTO knowledge_chunks" in str(c[0][0])]
        assert len(inserts) == 2

    @pytest.mark.asyncio
    async def test_flush_called(self):
        db = _make_db()
        params = {"file_path": "/tmp/doc.txt", "source_name": "T"}
        with _patch_extract(), _patch_chunker(), _patch_embedder():
            await DocumentIngesterAgent().run(_ctx(db, params))
        assert db.flush.call_count >= 1


# ── Embedding failure fallback ────────────────────────────────────────────────

class TestEmbeddingFallback:
    @pytest.mark.asyncio
    async def test_embedding_failure_stored_with_null(self):
        db = _make_db()
        params = {"file_path": "/tmp/doc.txt", "source_name": "T"}
        broken_embedder = MagicMock()
        broken_embedder.generate = AsyncMock(side_effect=Exception("OpenAI down"))
        with _patch_extract(), _patch_chunker(_SAMPLE_CHUNKS), \
             patch("agents.knowledge.document_ingester.EmbeddingGenerator", return_value=broken_embedder):
            result = await DocumentIngesterAgent().run(_ctx(db, params))
        assert result.status == "success"
        assert result.data["chunks_failed"] == 2
        assert result.data["chunks_created"] == 2

    @pytest.mark.asyncio
    async def test_partial_status_when_some_embeddings_fail(self):
        db = _make_db()
        params = {"file_path": "/tmp/doc.txt", "source_name": "T"}
        call_count = [0]
        async def _sometimes_fail(texts):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("fail")
            return [_FAKE_EMBEDDING]
        embedder = MagicMock()
        embedder.generate = _sometimes_fail
        with _patch_extract(), _patch_chunker(_SAMPLE_CHUNKS), \
             patch("agents.knowledge.document_ingester.EmbeddingGenerator", return_value=embedder):
            result = await DocumentIngesterAgent().run(_ctx(db, params))
        assert result.data["status"] == "partial"
