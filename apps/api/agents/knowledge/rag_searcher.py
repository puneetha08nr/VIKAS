"""rag_searcher — pgvector cosine similarity search over knowledge_chunks.

No LLM generation. Pure vector search:
  1. Embed the query string using EmbeddingGenerator (OpenAI text-embedding-3-small).
  2. Query knowledge_chunks using pgvector <=> (cosine distance) operator.
  3. Return top_k chunks ranked by similarity score descending.

If the embedding API is unavailable (missing key, network error) the agent
returns status="no_embedding_api" with an empty chunks list — it never crashes.

DB column note:
  knowledge_chunks uses `chunk_text` and `source_doc`, not `content`/`source`.
  The contract field names use the friendlier names; mapping is done in this module.

asyncpg named-param note:
  `::vector` cast conflicts with asyncpg's `:param` parser.
  Use `CAST(:query_vec AS vector)` instead (see ISSUES_AND_FIXES.md).
"""
import logging

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import RagSearcherOutput
from rag.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 5


@register
class RagSearcherAgent(BaseAgent):
    name = "rag_searcher"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        query = str(ctx.params.get("query", "")).strip()
        if not query:
            return AgentResult(status="failed", error="query param is required")

        top_k = max(1, int(ctx.params.get("top_k", _DEFAULT_TOP_K)))

        # ── Step 1: Embed query ───────────────────────────────────────────────
        try:
            embedding = await EmbeddingGenerator().generate_one(query)
        except Exception as exc:
            logger.warning("rag_searcher: embedding unavailable: %s", exc)
            return AgentResult(
                status="no_embedding_api",
                data={"chunks": [], "query": query, "total_found": 0},
                error=f"Embedding API unavailable: {exc}",
            )

        # ── Step 2: Vector search ─────────────────────────────────────────────
        rows = await _search_chunks(ctx.org_id, embedding, top_k, ctx.db)

        chunks: list[dict] = []
        for row in rows:
            try:
                output = RagSearcherOutput(
                    chunk_id=str(row[0]),
                    content=str(row[1]),
                    source=str(row[2]),
                    similarity_score=float(row[3]),
                )
                chunks.append(output.model_dump())
            except ValidationError as exc:
                logger.warning("rag_searcher: invalid chunk row skipped: %s", exc)

        return AgentResult(
            status="success",
            data={"chunks": chunks, "query": query, "total_found": len(chunks)},
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _search_chunks(
    org_id: str,
    embedding: list[float],
    top_k: int,
    db: AsyncSession,
) -> list:
    # Format as pgvector literal: '[0.1, 0.2, ...]'
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    result = await db.execute(
        text(
            "SELECT id, chunk_text, source_doc, "
            "1 - (embedding <=> CAST(:query_vec AS vector)) AS score "
            "FROM knowledge_chunks "
            "WHERE org_id = :org_id "
            "ORDER BY score DESC "
            "LIMIT :top_k"
        ),
        {"query_vec": vec_str, "org_id": org_id, "top_k": top_k},
    )
    return list(result.fetchall())
