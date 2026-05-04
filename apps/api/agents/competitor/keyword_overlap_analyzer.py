"""keyword_overlap_analyzer — finds which org keywords appear in competitor content.

No LLM, no external API. Pure SQL + Python string matching.

For each competitor_content row that has an extracted body, checks which of the
org's validated keywords appear (case-insensitive substring match) and writes
the matched keyword strings as a JSONB array to competitor_content.keywords_overlap.
"""
import json
import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import KeywordOverlapOutput

logger = logging.getLogger(__name__)


@register
class KeywordOverlapAnalyzerAgent(BaseAgent):
    name = "keyword_overlap_analyzer"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        keywords = await _fetch_validated_keywords(ctx.org_id, ctx.db)
        if not keywords:
            return AgentResult(
                status="success",
                data={"total_analyzed": 0, "message": "No validated keywords to match against"},
            )

        content_rows = await _fetch_content_with_body(ctx.org_id, ctx.db)
        if not content_rows:
            return AgentResult(
                status="success",
                data={"total_analyzed": 0, "message": "No competitor content with extracted body"},
            )

        kw_strings = [(str(row[0]), row[1].lower()) for row in keywords]

        total_updated = 0
        total_matches = 0

        for content in content_rows:
            body_lower = (content[2] or "").lower()
            matched = [kw for _, kw in kw_strings if kw in body_lower]

            try:
                output = KeywordOverlapOutput(
                    competitor_content_id=str(content[0]),
                    url=content[1],
                    matched_keywords=matched,
                    overlap_count=len(matched),
                )
            except ValidationError as exc:
                logger.warning(
                    "keyword_overlap_analyzer: validation error for %s: %s",
                    content[1], exc,
                )
                continue

            await _update_overlap(str(content[0]), output.matched_keywords, ctx.db)
            total_updated += 1
            total_matches += output.overlap_count

        await ctx.db.flush()

        return AgentResult(
            status="success",
            data={
                "total_analyzed": len(content_rows),
                "total_updated": total_updated,
                "total_keyword_matches": total_matches,
                "keywords_checked": len(keywords),
            },
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_validated_keywords(org_id: str, db: AsyncSession) -> list[Any]:
    result = await db.execute(
        text(
            "SELECT id, keyword FROM keywords "
            "WHERE org_id = :org_id AND status = 'validated' "
            "ORDER BY keyword"
        ),
        {"org_id": org_id},
    )
    return list(result.fetchall())


async def _fetch_content_with_body(org_id: str, db: AsyncSession) -> list[Any]:
    result = await db.execute(
        text(
            "SELECT id, url, body FROM competitor_content "
            "WHERE org_id = :org_id AND body IS NOT NULL AND body != '' "
            "ORDER BY id"
        ),
        {"org_id": org_id},
    )
    return list(result.fetchall())


async def _update_overlap(
    content_id: str, matched_keywords: list[str], db: AsyncSession
) -> None:
    await db.execute(
        text(
            "UPDATE competitor_content "
            "SET keywords_overlap = CAST(:overlap AS jsonb) "
            "WHERE id = :id"
        ),
        {"id": content_id, "overlap": json.dumps(matched_keywords)},
    )
