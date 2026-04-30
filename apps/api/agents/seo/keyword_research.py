import json
import logging
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


@register
class KeywordResearchAgent(BaseAgent):
    name = "keyword_research"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        seed = ctx.params["seed_keyword"]
        org_id = ctx.org_id

        # 1. Load prompt from registry — fails loudly if not seeded
        prompt_template = await PromptRegistry().get("keyword_research", ctx.db)

        # 2. Build prompt — substitute seed keyword into template
        prompt = prompt_template.replace("SEED_KEYWORD", seed)

        # 3. Call LLM — expect JSON list back
        response = await self.call_llm(ctx, prompt)
        print(f"[keyword_research] raw LLM response:\n{response}\n")

        # 4. Parse response safely
        keywords = _parse_keyword_json(response)

        # 5. Write to DB via RLS-scoped session
        await _save_keywords(keywords, org_id, agent_name=self.name, db=ctx.db)

        return AgentResult(
            status="success",
            data={"keywords_found": len(keywords), "seed": seed},
            tokens_used=ctx.llm.last_tokens_used,
            cost_usd=ctx.llm.last_cost_usd,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_keyword_json(response: str) -> list[dict[str, Any]]:
    """Extract a JSON array from the LLM response.

    Handles:
    - Clean JSON arrays
    - Arrays wrapped in markdown code fences
    - Partial or malformed JSON → returns empty list (logged as warning)
    """
    # Strip markdown code fences if present
    cleaned = re.sub(r"```(?:json)?\s*", "", response, flags=re.IGNORECASE).strip()
    # Find the outermost JSON array
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        logger.warning("keyword_research: no JSON array found in LLM response")
        return []

    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        logger.warning("keyword_research: JSON parse failed: %s", exc)
        return []

    if not isinstance(data, list):
        logger.warning("keyword_research: expected list, got %s", type(data).__name__)
        return []

    result = []
    for item in data:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str) and item.strip():
            # LLM returned a plain string array — wrap so _save_keywords can handle it uniformly
            result.append({"keyword": item.strip()})
        else:
            logger.warning("keyword_research: unexpected item type %s in response array, skipping", type(item).__name__)
    return result


async def _save_keywords(
    keywords: list[dict[str, Any]],
    org_id: str,
    agent_name: str,
    db: AsyncSession,
) -> None:
    """Bulk-insert keyword rows. Skips duplicates for this org via ON CONFLICT DO NOTHING."""
    if not keywords:
        return

    for kw in keywords:
        keyword_text = str(kw.get("keyword", "")).strip()
        if not keyword_text:
            continue

        await db.execute(
            text(
                "INSERT INTO keywords "
                "(id, org_id, keyword, volume, kd, cpc, intent, reason, status, source_agent, "
                "created_at, updated_at) "
                "VALUES "
                "(gen_random_uuid(), :org_id, :keyword, :volume, :kd, :cpc, "
                ":intent, :reason, 'raw', :source_agent, now(), now()) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "org_id": org_id,
                "keyword": keyword_text,
                "volume": _int_or_none(kw.get("volume") or kw.get("search_volume")),
                "kd": _float_or_none(kw.get("kd") or kw.get("keyword_difficulty") or kw.get("difficulty")),
                "cpc": _float_or_none(kw.get("cpc")),
                "intent": str(kw.get("intent") or kw.get("search_intent") or "").strip() or None,
                "reason": str(kw.get("reason") or kw.get("rationale") or kw.get("why") or "").strip() or None,
                "source_agent": agent_name,
            },
        )

    await db.flush()


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
