"""document_ingester — chunks and embeds uploaded documents into knowledge_chunks.

No LLM generation. Embeddings only.
  1. Reads file from file_path (PDF, DOCX, TXT, MD).
  2. Extracts plain text.
  3. Chunks via TextChunker (~500 tokens, 50 overlap).
  4. Embeds each chunk via EmbeddingGenerator (OpenAI text-embedding-3-small).
     If embedding fails → stores chunk with embedding=NULL, continues.
  5. Inserts rows into knowledge_chunks.

Input params:
  file_path   (str, required) — path to the file on disk
  source_name (str, optional) — display name; defaults to filename
  chunk_size  (int, optional, default 500) — target tokens per chunk
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import DocumentIngesterOutput
from rag.chunker import TextChunker
from rag.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


@register
class DocumentIngesterAgent(BaseAgent):
    name = "document_ingester"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        file_path = str(ctx.params.get("file_path", "")).strip()
        source_name = str(ctx.params.get("source_name", "")).strip()
        if not file_path:
            return AgentResult(status="failed", error="file_path param is required")

        path = Path(file_path)
        if not source_name:
            source_name = path.name

        ext = path.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            return AgentResult(
                status="failed",
                error=f"Unsupported file type '{ext}'. Supported: {sorted(_SUPPORTED_EXTENSIONS)}",
            )

        text_content = await _extract_text(path)
        if not text_content.strip():
            return AgentResult(status="failed", error=f"No text extracted from '{source_name}'")

        chunks = TextChunker().chunk(text_content, source_doc=source_name)
        if not chunks:
            return AgentResult(status="failed", error="Text produced zero chunks")

        embedder = EmbeddingGenerator()
        chunks_created = 0
        chunks_failed = 0

        for chunk in chunks:
            chunk_text = chunk["text"]
            embedding: list[float] | None = None
            try:
                vectors = await embedder.generate([chunk_text])
                embedding = vectors[0] if vectors else None
            except Exception as exc:
                logger.warning("document_ingester: embedding failed for chunk: %s", exc)
                chunks_failed += 1

            embedding_sql = (
                f"'[{','.join(str(x) for x in embedding)}]'::vector"
                if embedding
                else "NULL"
            )

            await ctx.db.execute(
                text(
                    "INSERT INTO knowledge_chunks "
                    "  (id, org_id, source_doc, chunk_text, embedding, metadata) "
                    "VALUES "
                    "  (gen_random_uuid(), :org_id, :source_doc, :chunk_text, "
                    f"  {embedding_sql}, CAST(:meta AS jsonb))"
                ),
                {
                    "org_id": ctx.org_id,
                    "source_doc": source_name,
                    "chunk_text": chunk_text,
                    "meta": (
                        f'{{"chunk_index": {chunk.get("chunk_index", 0)}, '
                        f'"token_count": {chunk.get("token_count", 0)}}}'
                    ),
                },
            )
            chunks_created += 1

        await ctx.db.flush()

        final_status = (
            "success" if chunks_failed == 0
            else "partial" if chunks_created > 0
            else "failed"
        )

        output = DocumentIngesterOutput(
            source_name=source_name,
            chunks_created=chunks_created,
            chunks_failed=chunks_failed,
            status=final_status,
        )
        return AgentResult(status="success", data=output.model_dump())


# ── Text extraction helpers ───────────────────────────────────────────────────

async def _extract_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in (".txt", ".md"):
        return _read_plain(path)
    if ext == ".pdf":
        return _read_pdf(path)
    if ext == ".docx":
        return _read_docx(path)
    return ""


def _read_plain(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        logger.warning("document_ingester: failed reading %s: %s", path, exc)
        return ""


def _read_pdf(path: Path) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(str(path))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    except Exception as exc:
        logger.warning("document_ingester: PDF read failed for %s: %s", path, exc)
        return ""


def _read_docx(path: Path) -> str:
    try:
        import docx
        doc = docx.Document(str(path))
        return "\n".join(p.text for p in doc.paragraphs if p.text)
    except Exception as exc:
        logger.warning("document_ingester: DOCX read failed for %s: %s", path, exc)
        return ""
