"""rank_tracker — records GSC keyword positions and flags quick-win opportunities.

No LLM. Fetches GSC search analytics, looks up each validated keyword,
writes a snapshot row to rank_tracking with status:
  - "ranking"     — position 1-10  (page 1)
  - "quick_win"   — position 11-30 (page 2-3, one push from page 1)
  - "not_ranking" — position > 30 or absent from GSC data
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
from core.contracts import RankTrackingOutput
from integrations.google_search_console import GoogleSearchConsoleIntegration

logger = logging.getLogger(__name__)

_DEFAULT_DAYS = 30
_QUICK_WIN_MIN = 11.0
_QUICK_WIN_MAX = 30.0


@register
class RankTrackerAgent(BaseAgent):
    name = "rank_tracker"
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
            logger.warning("rank_tracker: GSC unavailable: %s", exc)
            gsc_rows = []

        position_map: dict[str, float] = {
            row["query"].lower(): float(row["position"])
            for row in gsc_rows
            if row.get("query")
        }

        keywords = await _fetch_validated_keywords(ctx.org_id, ctx.db)
        if not keywords:
            return AgentResult(
                status="success",
                data={
                    "total_tracked": 0,
                    "quick_wins": 0,
                    "ranking": 0,
                    "not_ranking": 0,
                    "message": "No validated keywords to track",
                },
            )

        previous_positions = await _fetch_latest_positions(
            ctx.org_id, [str(k.id) for k in keywords], ctx.db
        )

        counts = {"quick_win": 0, "ranking": 0, "not_ranking": 0}

        for kw in keywords:
            position = position_map.get(kw.keyword.lower())
            status = _classify(position)
            prev = previous_positions.get(str(kw.id))

            try:
                output = RankTrackingOutput(
                    keyword=kw.keyword,
                    keyword_id=str(kw.id),
                    position=position,
                    previous_position=prev,
                    status=status,
                )
            except ValidationError as exc:
                logger.warning("rank_tracker: invalid output for %s: %s", kw.keyword, exc)
                continue

            await _insert_rank_snapshot(ctx.org_id, output, ctx.db)
            counts[status] += 1

        await ctx.db.flush()

        return AgentResult(
            status="success",
            data={
                "total_tracked": sum(counts.values()),
                "quick_wins": counts["quick_win"],
                "ranking": counts["ranking"],
                "not_ranking": counts["not_ranking"],
                "gsc_rows_fetched": len(gsc_rows),
                "site_url": site_url,
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
    return result.fetchall()


async def _fetch_latest_positions(
    org_id: str, keyword_ids: list[str], db: AsyncSession
) -> dict[str, float | None]:
    """Return {keyword_id: latest_position} for the most recent snapshot per keyword."""
    if not keyword_ids:
        return {}
    placeholders = ", ".join(f":kid_{i}" for i in range(len(keyword_ids)))
    params: dict[str, Any] = {f"kid_{i}": kid for i, kid in enumerate(keyword_ids)}
    params["org_id"] = org_id
    result = await db.execute(
        text(
            f"""
            SELECT DISTINCT ON (keyword_id) keyword_id, position
            FROM rank_tracking
            WHERE org_id = :org_id
              AND keyword_id IN ({placeholders})
            ORDER BY keyword_id, checked_at DESC
            """
        ),
        params,
    )
    return {str(row[0]): row[1] for row in result.fetchall()}


async def _insert_rank_snapshot(
    org_id: str, output: RankTrackingOutput, db: AsyncSession
) -> None:
    await db.execute(
        text(
            "INSERT INTO rank_tracking "
            "(id, org_id, keyword_id, keyword, position, previous_position, status, source, checked_at, created_at) "
            "VALUES "
            "(gen_random_uuid(), :org_id, :keyword_id, :keyword, "
            ":position, :previous_position, :status, 'gsc', now(), now())"
        ),
        {
            "org_id": org_id,
            "keyword_id": output.keyword_id,
            "keyword": output.keyword,
            "position": output.position,
            "previous_position": output.previous_position,
            "status": output.status,
        },
    )


# ── Classification ────────────────────────────────────────────────────────────

def _classify(position: float | None) -> str:
    if position is None or position > _QUICK_WIN_MAX:
        return "not_ranking"
    if position >= _QUICK_WIN_MIN:
        return "quick_win"
    return "ranking"
