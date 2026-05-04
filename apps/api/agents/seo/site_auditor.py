"""site_auditor — aggregates keyword position data into a site-level audit snapshot.

No LLM. Reads GSC search analytics and the rank_tracking table to compute:
  - total keywords tracked
  - ranking / quick_win / not_ranking counts
  - average GSC position across all ranked keywords
  - number of GSC rows fetched

Writes one snapshot row to site_audits per run.
"""
import json
import logging
from datetime import date, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import SiteAuditorOutput
from integrations.google_search_console import GoogleSearchConsoleIntegration

logger = logging.getLogger(__name__)

_DEFAULT_DAYS = 30


@register
class SiteAuditorAgent(BaseAgent):
    name = "site_auditor"
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
            logger.warning("site_auditor: GSC unavailable: %s", exc)
            gsc_rows = []

        # Latest rank_tracking snapshot per keyword
        rank_rows = await _fetch_latest_rank_snapshots(ctx.org_id, ctx.db)

        counts = {"ranking": 0, "quick_win": 0, "not_ranking": 0}
        positions: list[float] = []

        for row in rank_rows:
            status = row[0]
            position = row[1]
            if status in counts:
                counts[status] += 1
            if position is not None:
                positions.append(float(position))

        total = sum(counts.values())
        avg_pos = round(sum(positions) / len(positions), 1) if positions else None

        summary = {
            "site_url": site_url,
            "period_days": days,
            "gsc_rows_fetched": len(gsc_rows),
            "ranking": counts["ranking"],
            "quick_wins": counts["quick_win"],
            "not_ranking": counts["not_ranking"],
            "avg_position": avg_pos,
        }

        try:
            output = SiteAuditorOutput(
                org_id=ctx.org_id,
                site_url=site_url,
                total_keywords=total,
                ranking_count=counts["ranking"],
                quick_wins_count=counts["quick_win"],
                not_ranking_count=counts["not_ranking"],
                avg_position=avg_pos,
                gsc_rows_fetched=len(gsc_rows),
                summary=summary,
            )
        except ValidationError as exc:
            return AgentResult(status="failed", error=str(exc))

        await _insert_audit(output, ctx.db)
        await ctx.db.flush()

        return AgentResult(
            status="success",
            data=summary,
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_latest_rank_snapshots(org_id: str, db: AsyncSession) -> list[Any]:
    """Return the most recent status + position per keyword."""
    result = await db.execute(
        text(
            """
            SELECT DISTINCT ON (keyword_id) status, position
            FROM rank_tracking
            WHERE org_id = :org_id
            ORDER BY keyword_id, checked_at DESC
            """
        ),
        {"org_id": org_id},
    )
    return list(result.fetchall())


async def _insert_audit(output: SiteAuditorOutput, db: AsyncSession) -> None:
    await db.execute(
        text(
            "INSERT INTO site_audits "
            "(id, org_id, site_url, audit_date, total_keywords, ranking_count, "
            "quick_wins_count, not_ranking_count, avg_position, "
            "gsc_rows_fetched, summary, created_at) "
            "VALUES "
            "(gen_random_uuid(), :org_id, :site_url, CURRENT_DATE, :total_keywords, "
            ":ranking_count, :quick_wins_count, :not_ranking_count, :avg_position, "
            ":gsc_rows_fetched, CAST(:summary AS jsonb), now())"
        ),
        {
            "org_id": output.org_id,
            "site_url": output.site_url,
            "total_keywords": output.total_keywords,
            "ranking_count": output.ranking_count,
            "quick_wins_count": output.quick_wins_count,
            "not_ranking_count": output.not_ranking_count,
            "avg_position": output.avg_position,
            "gsc_rows_fetched": output.gsc_rows_fetched,
            "summary": json.dumps(output.summary),
        },
    )
