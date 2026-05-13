#!/usr/bin/env python
"""Ingest knowledge documents into knowledge_chunks table for RAG.

Reads all .md files from apps/api/knowledge/ and seeds them into the
knowledge_chunks table using keyword-based chunking (no embeddings needed).

Usage:
    python scripts/ingest_knowledge.py
    python scripts/ingest_knowledge.py --clear  # clear existing chunks first
"""
import asyncio
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from sqlalchemy import text
from db.session import AsyncSessionLocal

ORG_ID = "00000000-0000-0000-0000-000000000001"
KNOWLEDGE_DIR = Path(__file__).parent.parent / "apps" / "api" / "knowledge"
CHUNK_SIZE = 400  # words per chunk
CHUNK_OVERLAP = 50  # words overlap between chunks


def chunk_text(text: str, source: str) -> list[dict]:
    """Split text into overlapping chunks."""
    # Split on double newlines (paragraphs) first
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    chunks = []
    current_chunk = []
    current_words = 0

    for para in paragraphs:
        words = para.split()
        if current_words + len(words) > CHUNK_SIZE and current_chunk:
            # Save current chunk
            chunk_text = '\n\n'.join(current_chunk)
            chunks.append({
                "id": str(uuid.uuid4()),
                "source_doc": source,
                "chunk_text": chunk_text,
                "metadata": {"source": source, "words": current_words},
            })
            # Keep overlap
            overlap_text = ' '.join(' '.join(current_chunk).split()[-CHUNK_OVERLAP:])
            current_chunk = [overlap_text] if overlap_text else []
            current_words = len(overlap_text.split()) if overlap_text else 0

        current_chunk.append(para)
        current_words += len(words)

    # Save last chunk
    if current_chunk:
        chunk_text_str = '\n\n'.join(current_chunk)
        chunks.append({
            "id": str(uuid.uuid4()),
            "source_doc": source,
            "chunk_text": chunk_text_str,
            "metadata": {"source": source, "words": current_words},
        })

    return chunks


async def ingest(clear: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text(f"SET app.current_org_id = '{ORG_ID}'"))

        if clear:
            await db.execute(
                text("DELETE FROM knowledge_chunks WHERE org_id = :org_id"),
                {"org_id": ORG_ID},
            )
            print("  CLEAR  existing knowledge chunks")

        if not KNOWLEDGE_DIR.exists():
            print(f"  ERROR  knowledge dir not found: {KNOWLEDGE_DIR}")
            return

        md_files = list(KNOWLEDGE_DIR.glob("*.md"))
        if not md_files:
            print("  ERROR  no .md files found in knowledge/")
            return

        total_chunks = 0
        for md_file in sorted(md_files):
            content = md_file.read_text(encoding="utf-8")
            source = md_file.stem  # e.g. "faq", "how_it_works"
            chunks = chunk_text(content, source)

            for chunk in chunks:
                await db.execute(
                    text(
                        "INSERT INTO knowledge_chunks "
                        "  (id, org_id, source_doc, chunk_text, metadata, created_at) "
                        "VALUES "
                        "  (CAST(:id AS uuid), :org_id, :source_doc, :chunk_text, "
                        "   CAST(:metadata AS jsonb), now()) "
                        "ON CONFLICT DO NOTHING"
                    ),
                    {
                        "id": chunk["id"],
                        "org_id": ORG_ID,
                        "source_doc": chunk["source_doc"],
                        "chunk_text": chunk["chunk_text"],
                        "metadata": str(chunk["metadata"]).replace("'", '"'),
                    },
                )
            total_chunks += len(chunks)
            print(f"  SEED  {md_file.name} - {len(chunks)} chunks")

        await db.commit()
        print(f"\n  Done. {total_chunks} total chunks ingested.")
        print(f"  RAG is ready — chat will now use knowledge base.")


if __name__ == "__main__":
    clear = "--clear" in sys.argv
    asyncio.run(ingest(clear=clear))
