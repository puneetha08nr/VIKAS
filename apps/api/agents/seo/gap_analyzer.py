"""gap_analyzer — scores competitive gap for each opportunity using GSC + competitor content.

No LLM. Reads opportunities, fetches our GSC positions, counts how many competitor
pages cover each keyword, then writes a gap score to opportunities.competitive_gap_score.

Gap score formula (0-10):
  coverage_score  = min(5.0, competitor_pages * 1.5)   — more coverage = higher gap
  position_score  = 5.0 (no rank) | 4.0 (>30) | 3.0 (11-30) | 1.0 (1-10)
  gap_score       = coverage_score + position_score    (clamped to 0-10)
"""
import logging
from datetime import date, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import GapAnalysisOutput
from integrations.google_search_console import GoogleSearchConsoleIntegration

logger = logging.getLogger(__name__)

_DEFAULT_DAYS = 30


@register
class GapAnalyzerAgent(BaseAgent):
    name = "gap_analyzer"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        site_url = ctx.params.get("site_url") or settings.gsc_site_url
        if not site_url:
            return AgentResult(
                status="failed",
                error="site_url required — pass as param or set GSC_SITE_URL in .env",
            )

        days = int(ctx.params.get("days", _DEFAULT_DAYS))
        end = date.today()
        start = end - timedelta(days=days)

        gsc = GoogleSearchConsoleIntegration()
        try:
            gsc_rows = await gsc.get_search_analytics(
                site_url=site_url,
                start_date=start,
                end_date=end,
                dimensions=["query"],
                row_limit=1000,
            )
        except Exception as exc:
            logger.warning("gap_analyzer: GSC unavailable: %s", exc)
            gsc_rows = []

        position_map: dict[str, float] = {
            row["query"].lower(): float(row["position"])
            for row in gsc_rows
            if row.get("query")
        }

        opps = await _fetch_opportunities(ctx.org_id, ctx.db)
        if not opps:
            return AgentResult(
                status="success",
                data={
                    "gaps_scored": 0,
                    "keywords_in_gsc": 0,
                    "site_url": site_url,
                    "message": "No opportunities to score",
                },
            )

        gaps_scored = 0
        in_gsc = 0

        for opp in opps:
            keyword_lower = opp.keyword.lower()
            our_position = position_map.get(keyword_lower)
            if our_position is not None:
                in_gsc += 1

            competitor_pages = await _count_competitor_mentions(
                opp.keyword, ctx.org_id, ctx.db
            )
            gap_score = _compute_gap_score(our_position, competitor_pages)

            try:
                output = GapAnalysisOutput(
                    keyword=opp.keyword,
                    keyword_id=str(opp.keyword_id),
                    competitive_gap_score=gap_score,
                    our_position=our_position,
                    competitor_pages_found=competitor_pages,
                )
            except ValidationError as exc:
                logger.warning("gap_analyzer: invalid output for %s: %s", opp.keyword, exc)
                continue

            await _update_gap_score(str(opp.id), output.competitive_gap_score, ctx.db)
            gaps_scored += 1

        await ctx.db.flush()

        return AgentResult(
            status="success",
            data={
                "gaps_scored": gaps_scored,
                "keywords_in_gsc": in_gsc,
                "gsc_rows_fetched": len(gsc_rows),
                "site_url": site_url,
            },
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_opportunities(org_id: str, db: AsyncSession) -> list[Any]:
    result = await db.execute(
        text("""
            SELECT o.id, o.keyword_id, k.keyword
            FROM opportunities o
            JOIN keywords k ON o.keyword_id = k.id
            WHERE o.org_id = :org_id
            ORDER BY o.created_at
        """),
        {"org_id": org_id},
    )
    return list(result.fetchall())


async def _count_competitor_mentions(keyword: str, org_id: str, db: AsyncSession) -> int:
    result = await db.execute(
        text("""
            SELECT COUNT(*) FROM competitor_content
            WHERE org_id = :org_id
              AND body IS NOT NULL
              AND body ILIKE '%' || :keyword || '%'
        """),
        {"org_id": org_id, "keyword": keyword},
    )
    row = result.fetchone()
    return int(row[0]) if row else 0


async def _update_gap_score(opp_id: str, gap_score: float, db: AsyncSession) -> None:
    await db.execute(
        text(
            "UPDATE opportunities SET competitive_gap_score = :gap_score "
            "WHERE id = :id"
        ),
        {"id": opp_id, "gap_score": gap_score},
    )


# ── Scoring ───────────────────────────────────────────────────────────────────

def _compute_gap_score(our_position: float | None, competitor_pages: int) -> float:
    coverage_score = min(5.0, competitor_pages * 1.5)

    if our_position is None:
        position_score = 5.0
    elif our_position > 30:
        position_score = 4.0
    elif our_position > 10:
        position_score = 3.0
    else:
        position_score = 1.0

    return round(min(10.0, coverage_score + position_score), 2)
