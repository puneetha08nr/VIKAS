"""internal_link_finder — suggests internal links for a piece of content.

No LLM. Two-signal scoring:

  1. Semantic (via pgvector): embeds the query and searches knowledge_chunks
     for similar content. source_doc paths from top results are matched
     against published content titles to produce a rag_boost (0.2).

  2. Keyword overlap: counts how many query words appear in each published
     title, normalised to [0, 1].

  final_score = min(1.0, keyword_overlap + rag_boost)

Input params:
  query   (str)  — article text, title, or keyword to find links for
  top_k   (int)  — max suggestions to return (default 5)

Source table: content_items WHERE status='published' AND published_url IS NOT NULL
Vector index:  knowledge_chunks (same embedding space used by rag_searcher)

Graceful degradation:
  If the embedding API is unavailable, the agent continues with keyword-only
  scoring (rag_boost is skipped) and still returns useful suggestions.
"""
import logging

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import InternalLinkOutput
from rag.embeddings import EmbeddingGenerator

logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 5
_RAG_BOOST = 0.2       # added when a rag chunk's source matches a title word
_RAG_FETCH_K = 10      # fetch more rag results than needed to improve coverage


@register
class InternalLinkFinderAgent(BaseAgent):
    name = "internal_link_finder"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        query = str(ctx.params.get("query", "")).strip()
        if not query:
            return AgentResult(status="failed", error="query param is required")

        top_k = max(1, int(ctx.params.get("top_k", _DEFAULT_TOP_K)))

        # ── Step 1: Semantic search of knowledge_chunks ───────────────────────
        rag_sources: set[str] = set()
        try:
            embedding = await EmbeddingGenerator().generate_one(query)
            rag_rows = await _search_chunks(ctx.org_id, embedding, _RAG_FETCH_K, ctx.db)
            for row in rag_rows:
                rag_sources.add(str(row[2]).lower())  # source_doc
        except Exception as exc:
            logger.warning("internal_link_finder: embedding unavailable, skipping rag: %s", exc)

        # ── Step 2: Fetch published content items ─────────────────────────────
        published = await _fetch_published(ctx.org_id, ctx.db)
        if not published:
            return AgentResult(
                status="success",
                data={"links": [], "total_found": 0, "query": query},
            )

        # ── Step 3: Score each published item ─────────────────────────────────
        query_words = {w for w in query.lower().split() if len(w) > 2}
        scored: list[dict] = []

        for row in published:
            title = str(row[1] or "").strip()
            published_url = str(row[2])

            if not title or not published_url:
                continue

            # Keyword overlap: fraction of query words found in title
            title_lower = title.lower()
            matched_words = sum(1 for w in query_words if w in title_lower)
            kw_score = matched_words / max(len(query_words), 1)

            # RAG boost: any rag source_doc contains a significant title word
            title_words = [w for w in title.lower().split() if len(w) > 3]
            rag_boost = (
                _RAG_BOOST
                if rag_sources and any(
                    any(tw in src for src in rag_sources)
                    for tw in title_words
                )
                else 0.0
            )

            score = round(min(1.0, kw_score + rag_boost), 4)

            try:
                output = InternalLinkOutput(
                    url=published_url,
                    title=title,
                    anchor_text=title,
                    similarity_score=score,
                )
                scored.append(output.model_dump())
            except ValidationError as exc:
                logger.warning("internal_link_finder: invalid item skipped: %s", exc)

        scored.sort(key=lambda x: x["similarity_score"], reverse=True)
        links = scored[:top_k]

        return AgentResult(
            status="success",
            data={"links": links, "total_found": len(links), "query": query},
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_published(org_id: str, db: AsyncSession) -> list:
    result = await db.execute(
        text(
            "SELECT id, title, published_url "
            "FROM content_items "
            "WHERE org_id = :org_id "
            "  AND status = 'published' "
            "  AND published_url IS NOT NULL "
            "ORDER BY updated_at DESC"
        ),
        {"org_id": org_id},
    )
    return list(result.fetchall())


async def _search_chunks(
    org_id: str,
    embedding: list[float],
    top_k: int,
    db: AsyncSession,
) -> list:
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
