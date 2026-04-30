import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from rag.embeddings import EmbeddingGenerator


class RAGRetriever:

    def __init__(self, embeddings: EmbeddingGenerator | None = None) -> None:
        self._embeddings = embeddings or EmbeddingGenerator()

    async def search(
        self,
        query: str,
        org_id: str,
        db: AsyncSession,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Cosine-similarity search over knowledge_chunks scoped to org_id.

        Relies on the RLS variable ``app.current_org_id`` already being set
        on the session (done by ``org_session`` context manager in db/session.py).
        """
        query_vector = await self._embeddings.generate_one(query)
        vector_literal = "[" + ",".join(str(v) for v in query_vector) + "]"

        result = await db.execute(
            text(
                "SELECT chunk_text, source_doc, metadata, "
                "1 - (embedding <=> :vector::vector) AS similarity "
                "FROM knowledge_chunks "
                "WHERE org_id = current_setting('app.current_org_id')::uuid "
                "ORDER BY embedding <=> :vector::vector "
                "LIMIT :top_k"
            ),
            {"vector": vector_literal, "top_k": top_k},
        )

        rows = result.fetchall()
        return [
            {
                "chunk_text": row[0],
                "source_doc": row[1],
                "metadata": row[2] if isinstance(row[2], dict) else {},
                "similarity": float(row[3]),
            }
            for row in rows
        ]
