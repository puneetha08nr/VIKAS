"""brand_voice_keeper — stores and retrieves org brand voice configuration.

No LLM. Accepts explicit brand voice params (tone, vocabulary, banned_phrases,
style_rules) and UPSERTs them into the brand_voice table (one row per org).
If no params are provided, returns the current brand voice state.

Typical callers:
  - Settings UI (user fills in brand voice form → this agent persists it)
  - Preference learner (aggregated style patterns → this agent stores them)
"""
import json
import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import BrandVoiceOutput

logger = logging.getLogger(__name__)


@register
class BrandVoiceKeeperAgent(BaseAgent):
    name = "brand_voice_keeper"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        current = await _fetch_current(ctx.org_id, ctx.db)

        # Merge incoming params over whatever is already stored
        tone = ctx.params.get("tone", current.get("tone", ""))
        vocabulary = ctx.params.get("vocabulary", current.get("vocabulary", []))
        banned_phrases = ctx.params.get("banned_phrases", current.get("banned_phrases", []))
        style_rules = ctx.params.get("style_rules", current.get("style_rules", {}))

        try:
            output = BrandVoiceOutput(
                org_id=ctx.org_id,
                tone=tone,
                vocabulary=vocabulary,
                banned_phrases=banned_phrases,
                style_rules=style_rules,
            )
        except ValidationError as exc:
            return AgentResult(
                status="failed",
                error=f"brand_voice_keeper: invalid params: {exc}",
            )

        updated = await _upsert_brand_voice(ctx.org_id, output, ctx.db)
        await ctx.db.flush()

        content_stats = await _fetch_content_stats(ctx.org_id, ctx.db)

        return AgentResult(
            status="success",
            data={
                "action": "updated" if updated else "unchanged",
                "tone": output.tone,
                "vocabulary_terms": len(output.vocabulary),
                "banned_phrases": len(output.banned_phrases),
                "style_rules": len(output.style_rules),
                "content_approved": content_stats["approved"],
                "content_published": content_stats["published"],
            },
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_current(org_id: str, db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        text(
            "SELECT tone, vocabulary, banned_phrases, style_rules "
            "FROM brand_voice WHERE org_id = :org_id"
        ),
        {"org_id": org_id},
    )
    row = result.fetchone()
    if row is None:
        return {"tone": "", "vocabulary": [], "banned_phrases": [], "style_rules": {}}
    return {
        "tone": row[0] or "",
        "vocabulary": row[1] if isinstance(row[1], list) else [],
        "banned_phrases": row[2] if isinstance(row[2], list) else [],
        "style_rules": row[3] if isinstance(row[3], dict) else {},
    }


async def _upsert_brand_voice(
    org_id: str, output: BrandVoiceOutput, db: AsyncSession
) -> bool:
    """UPSERT brand_voice row. Returns True if a write was performed."""
    result = await db.execute(
        text(
            "INSERT INTO brand_voice "
            "(id, org_id, tone, vocabulary, banned_phrases, style_rules, updated_at) "
            "VALUES (gen_random_uuid(), :org_id, :tone, "
            "CAST(:vocabulary AS jsonb), CAST(:banned_phrases AS jsonb), "
            "CAST(:style_rules AS jsonb), now()) "
            "ON CONFLICT (org_id) DO UPDATE SET "
            "  tone = EXCLUDED.tone, "
            "  vocabulary = EXCLUDED.vocabulary, "
            "  banned_phrases = EXCLUDED.banned_phrases, "
            "  style_rules = EXCLUDED.style_rules, "
            "  updated_at = now() "
            "RETURNING id"
        ),
        {
            "org_id": org_id,
            "tone": output.tone,
            "vocabulary": json.dumps(output.vocabulary),
            "banned_phrases": json.dumps(output.banned_phrases),
            "style_rules": json.dumps(output.style_rules),
        },
    )
    return result.fetchone() is not None


async def _fetch_content_stats(org_id: str, db: AsyncSession) -> dict[str, int]:
    result = await db.execute(
        text(
            "SELECT status, COUNT(*) FROM content_items "
            "WHERE org_id = :org_id AND status IN ('approved', 'published') "
            "GROUP BY status"
        ),
        {"org_id": org_id},
    )
    stats = {"approved": 0, "published": 0}
    for row in result.fetchall():
        if row[0] in stats:
            stats[row[0]] = int(row[1])
    return stats
