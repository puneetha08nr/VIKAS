"""threat_assessor — pure rules engine that scores competitor content threat level.

No LLM, no external API. Two sub-scores combine into a single threat_score:

  keyword_overlap_score (0-10): count of org's validated keywords found in
    the competitor page body (case-insensitive substring), capped at 10.

  content_depth_score (0-10): derived from word_count:
    > 2000 words → 10  (comprehensive, long-form)
    > 1000 words →  7  (solid depth)
    >  500 words →  4  (moderate)
    ≤  500 words →  2  (thin)

  threat_score = (keyword_overlap_score * 0.6) + (content_depth_score * 0.4)

Only processes rows where threat_score IS NULL (idempotent — safe to re-run).
"""
import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import ThreatAssessorOutput

logger = logging.getLogger(__name__)


@register
class ThreatAssessorAgent(BaseAgent):
    name = "threat_assessor"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        keywords = await _fetch_validated_keywords(ctx.org_id, ctx.db)

        content_rows = await _fetch_unscored_content(ctx.org_id, ctx.db)
        if not content_rows:
            return AgentResult(
                status="success",
                data={
                    "total_scored": 0,
                    "message": "No unscored competitor content found",
                },
            )

        kw_strings = [str(row[0]).lower() for row in keywords]
        total_scored = 0
        score_sum = 0.0

        for row in content_rows:
            content_id = str(row[0])
            url = str(row[1])
            word_count = int(row[2] or 0)
            body = str(row[3] or "").lower()

            match_count = sum(1 for kw in kw_strings if kw in body)
            overlap_score = min(10.0, float(match_count))
            depth_score = _depth_score(word_count)
            threat = round((overlap_score * 0.6) + (depth_score * 0.4), 3)

            try:
                output = ThreatAssessorOutput(
                    competitor_content_id=content_id,
                    url=url,
                    keyword_overlap_score=overlap_score,
                    content_depth_score=depth_score,
                    threat_score=threat,
                )
            except ValidationError as exc:
                logger.warning("threat_assessor: validation error for %s: %s", url, exc)
                continue

            await _update_threat_score(content_id, output.threat_score, ctx.db)
            total_scored += 1
            score_sum += output.threat_score

        await ctx.db.flush()

        avg = round(score_sum / total_scored, 3) if total_scored else 0.0
        return AgentResult(
            status="success",
            data={
                "total_scored": total_scored,
                "avg_threat_score": avg,
                "keywords_used": len(kw_strings),
            },
        )


# ── Scoring ───────────────────────────────────────────────────────────────────

def _depth_score(word_count: int) -> float:
    if word_count > 2000:
        return 10.0
    if word_count > 1000:
        return 7.0
    if word_count > 500:
        return 4.0
    return 2.0


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_validated_keywords(org_id: str, db: AsyncSession) -> list[Any]:
    result = await db.execute(
        text(
            "SELECT keyword FROM keywords "
            "WHERE org_id = :org_id AND status = 'validated' "
            "ORDER BY keyword"
        ),
        {"org_id": org_id},
    )
    return list(result.fetchall())


async def _fetch_unscored_content(org_id: str, db: AsyncSession) -> list[Any]:
    result = await db.execute(
        text(
            "SELECT id, url, word_count, body "
            "FROM competitor_content "
            "WHERE org_id = :org_id "
            "  AND body IS NOT NULL "
            "  AND threat_score IS NULL "
            "ORDER BY id"
        ),
        {"org_id": org_id},
    )
    return list(result.fetchall())


async def _update_threat_score(
    content_id: str, score: float, db: AsyncSession
) -> None:
    await db.execute(
        text(
            "UPDATE competitor_content "
            "SET threat_score = :score "
            "WHERE id = :id"
        ),
        {"id": content_id, "score": score},
    )
