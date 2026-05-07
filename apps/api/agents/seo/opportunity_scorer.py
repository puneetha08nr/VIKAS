import logging

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import OpportunityOutput

logger = logging.getLogger(__name__)


# ── Scoring dimensions ────────────────────────────────────────────────────────

class ScoringDimension:
    name: str
    weight: float

    async def score(self, keyword, org_id, db) -> float:
        raise NotImplementedError


class SearchPotentialDimension(ScoringDimension):
    name = "search_potential"
    weight = 0.40

    async def score(self, keyword, org_id, db) -> float:
        volume = int(keyword.volume or 0)
        kd = float(keyword.kd or 0.0)
        return round(min(10.0, (volume / 5000) * max(0.0, 10.0 - kd)), 3)


class CompetitiveGapDimension(ScoringDimension):
    name = "competitive_gap"
    weight = 0.30

    async def score(self, keyword, org_id, db) -> float:
        return 5.0


class EngagementDimension(ScoringDimension):
    name = "engagement"
    weight = 0.10

    async def score(self, keyword, org_id, db) -> float:
        cpc = float(keyword.cpc or 0.0)
        return round(min(10.0, cpc * 0.8), 3)


DIMENSIONS: list[ScoringDimension] = [
    SearchPotentialDimension(),
    CompetitiveGapDimension(),
    EngagementDimension(),
]

_INTENT_MULTIPLIER = {
    "commercial": 1.5,
    "transactional": 1.3,
    "informational": 1.0,
    "navigational": 0.3,
}


async def _get_real_trend_score(keyword_text: str, org_id: str, db) -> float | None:
    """Return momentum (0-10) from the latest non-neutral trend signal, or None."""
    result = await db.execute(
        text("""
            SELECT momentum FROM trend_signals
            WHERE org_id = :org_id
              AND query = :query
              AND source != 'neutral_fallback'
            ORDER BY detected_at DESC LIMIT 1
        """),
        {"org_id": org_id, "query": keyword_text},
    )
    row = result.fetchone()
    return float(row.momentum) if row else None


async def compute_composite(keyword, org_id, db) -> dict:
    """Score a keyword across all dimensions. trend_score is NULL when no real signal exists."""
    intent_multiplier = _INTENT_MULTIPLIER.get(
        str(keyword.intent or "informational").lower(), 1.0
    )

    scores: dict[str, float] = {}
    weighted_sum = 0.0
    for dim in DIMENSIONS:
        s = await dim.score(keyword, org_id, db)
        scores[dim.name] = s
        weighted_sum += s * dim.weight

    # Trend: use real signal if available, else leave NULL for Mode 2 to fill later
    trend_score = await _get_real_trend_score(keyword.keyword, org_id, db)
    if trend_score is not None:
        weighted_sum += trend_score * 0.20

    composite = round(min(weighted_sum * intent_multiplier, 10.0), 3)

    return {
        "composite_score": composite,
        "search_score": scores["search_potential"],
        "competitive_gap_score": scores["competitive_gap"],
        "trend_score": trend_score,          # None when no real data yet
        "engagement_score": scores["engagement"],
    }


def _recalculate_composite(
    search_score: float | None,
    gap_score: float | None,
    trend_score: float | None,
    engage_score: float | None,
) -> float:
    """Recalculate composite as simple average of available non-None scores, capped at 10."""
    available = [s for s in [search_score, gap_score, trend_score, engage_score] if s is not None]
    if not available:
        return 0.0
    return min(round(sum(available) / len(available), 2), 10.0)


# ── Agent ─────────────────────────────────────────────────────────────────────

@register
class OpportunityScorerAgent(BaseAgent):
    name = "opportunity_scorer"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        org_id = ctx.org_id
        keyword_ids: list[str] = ctx.params.get("keyword_ids", [])

        created = await _mode1_create(org_id, keyword_ids, ctx)
        updated = await _mode2_update(org_id, ctx)

        await ctx.db.flush()

        if created == 0 and updated == 0:
            return AgentResult(
                status="success",
                data={
                    "opportunities_created": 0,
                    "opportunities_updated": 0,
                    "message": "No unscored validated keywords found and no trend true-ups needed",
                },
                tokens_used=0,
                cost_usd=0.0,
            )

        return AgentResult(
            status="success",
            data={
                "opportunities_created": created,
                "opportunities_updated": updated,
                "message": f"Created {created}, updated {updated} with trend data",
            },
            tokens_used=0,
            cost_usd=0.0,
        )


# ── Mode 1: Create new opportunities ─────────────────────────────────────────

async def _mode1_create(org_id: str, keyword_ids: list[str], ctx: AgentContext) -> int:
    """Create opportunities for validated keywords that have no existing opportunity."""
    if keyword_ids:
        where_clause = """
            k.status = 'validated'
            AND k.id = ANY(:keyword_ids)
            AND NOT EXISTS (
                SELECT 1 FROM opportunities o WHERE o.keyword_id = k.id
            )
        """
        params: dict = {"org_id": org_id, "keyword_ids": keyword_ids}
    else:
        where_clause = """
            k.status = 'validated'
            AND NOT EXISTS (
                SELECT 1 FROM opportunities o WHERE o.keyword_id = k.id
            )
        """
        params = {"org_id": org_id}

    result = await ctx.db.execute(
        text(f"""
            SELECT k.id, k.keyword, k.volume, k.kd, k.cpc, k.intent
            FROM keywords k
            WHERE k.org_id = :org_id
              AND {where_clause}
            ORDER BY k.volume DESC
        """),
        params,
    )
    keywords = result.fetchall()

    created = 0
    for kw in keywords:
        scored = await compute_composite(kw, org_id, ctx.db)

        output = OpportunityOutput(
            keyword_id=str(kw.id),
            org_id=org_id,
            **scored,
        )

        await ctx.db.execute(
            text("""
                INSERT INTO opportunities (
                    id, org_id, keyword_id, source,
                    search_score, competitive_gap_score,
                    trend_score, engagement_score,
                    composite_score, status,
                    format_fit_scores,
                    created_at
                ) VALUES (
                    gen_random_uuid(), :org_id, :keyword_id, :source,
                    :search_score, :gap_score,
                    :trend_score, :engagement_score,
                    :composite_score, 'new',
                    '{}',
                    now()
                )
                ON CONFLICT DO NOTHING
            """),
            {
                "org_id": org_id,
                "keyword_id": output.keyword_id,
                "source": output.source,
                "search_score": output.search_score,
                "gap_score": output.competitive_gap_score,
                "trend_score": output.trend_score,
                "engagement_score": output.engagement_score,
                "composite_score": output.composite_score,
            },
        )
        created += 1

    return created


# ── Mode 2: True-up trend scores for existing opportunities ───────────────────

async def _mode2_update(org_id: str, ctx: AgentContext) -> int:
    """Update existing opportunities whose trend_score is missing or was a placeholder.

    Targets rows where trend_score IS NULL (created after fix) or = 5.0 (old placeholder),
    and a non-neutral trend signal now exists for the keyword.
    """
    result = await ctx.db.execute(
        text("""
            SELECT o.id,
                   o.search_score,
                   o.competitive_gap_score,
                   o.engagement_score,
                   ts.momentum AS new_trend_score
            FROM opportunities o
            JOIN keywords k ON k.id = o.keyword_id
            JOIN trend_signals ts
              ON ts.query = k.keyword
             AND ts.org_id = o.org_id
             AND ts.detected_at = (
                     SELECT MAX(detected_at)
                     FROM trend_signals
                     WHERE query = k.keyword
                       AND org_id = o.org_id
                 )
            WHERE o.org_id = :org_id
              AND (o.trend_score IS NULL OR o.trend_score = 5)
              AND ts.source != 'neutral_fallback'
        """),
        {"org_id": org_id},
    )
    rows = result.fetchall()

    updated = 0
    for row in rows:
        new_composite = _recalculate_composite(
            search_score=float(row.search_score) if row.search_score is not None else None,
            gap_score=(
                float(row.competitive_gap_score) if row.competitive_gap_score is not None else None
            ),
            trend_score=float(row.new_trend_score),
            engage_score=float(row.engagement_score) if row.engagement_score is not None else None,
        )

        await ctx.db.execute(
            text("""
                UPDATE opportunities
                SET trend_score = :trend_score,
                    composite_score = :composite_score
                WHERE id = :id
            """),
            {
                "id": str(row.id),
                "trend_score": float(row.new_trend_score),
                "composite_score": new_composite,
            },
        )
        updated += 1

    return updated
