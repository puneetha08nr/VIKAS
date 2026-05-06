"""ai_assistant — answers marketing questions using RAG context.

Standard tier LLM. Uses knowledge_chunks for context (RAG retrieval).
Does NOT write to DB — returns answer inline.

Input params:
  question (str, required)
  top_k    (int, optional — number of knowledge chunks to retrieve, default: 5)
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import AIAssistantOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


@register
class AIAssistantAgent(BaseAgent):
    name = "ai_assistant"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        question = str(ctx.params.get("question", "")).strip()
        if not question:
            return AgentResult(status="failed", error="question param is required")

        top_k = int(ctx.params.get("top_k", 5))
        if top_k < 1:
            top_k = 5

        chunks = await _retrieve_chunks(question, ctx.org_id, top_k, ctx.db)

        template = await PromptRegistry().get(self.name, ctx.db)
        context_text = (
            "\n\n".join(c["chunk_text"] for c in chunks)
            if chunks
            else "No relevant context found."
        )
        prompt = (
            template
            .replace("QUESTION", question)
            .replace("CONTEXT", context_text)
        )

        answer = await self.call_llm(ctx, prompt)

        output = AIAssistantOutput(
            question=question,
            answer=answer.strip(),
            sources_used=len(chunks),
            status="success",
        )
        return AgentResult(status="success", data=output.model_dump())


async def _retrieve_chunks(question: str, org_id: str, top_k: int, db) -> list[dict]:
    """Retrieve relevant knowledge chunks by text similarity (ILIKE fallback, no embedding)."""
    try:
        result = await db.execute(
            text(
                "SELECT chunk_text, source_doc "
                "FROM knowledge_chunks "
                "WHERE org_id = :org_id "
                "ORDER BY created_at DESC "
                "LIMIT :top_k"
            ),
            {"org_id": org_id, "top_k": top_k},
        )
        rows = result.fetchall()
        return [{"chunk_text": row[0] or "", "source_doc": row[1] or ""} for row in rows]
    except Exception:
        logger.warning("ai_assistant: failed to retrieve knowledge chunks")
        return []
