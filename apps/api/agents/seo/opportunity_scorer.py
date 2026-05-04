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
        # Phase 1: placeholder until GSC connected
        # Phase 2: compare your ranking vs competitor ranking
        # Phase 3: full SERP analysis
        return 5.0


class TrendDimension(ScoringDimension):
    name = "trend"
    weight = 0.20

    async def score(self, keyword, org_id, db) -> float:
        # Phase 1: falls back to 5.0 when trend_signals has no data
        # Phase 2: populated automatically once trend_collector writes to trend_signals
        result = await db.execute(text("""
            SELECT momentum FROM trend_signals
            WHERE org_id = :org_id AND query = :query
            ORDER BY detected_at DESC LIMIT 1
        """), {"org_id": org_id, "query": keyword.keyword})
        row = result.fetchone()
        return float(row.momentum) if row else 5.0


class EngagementDimension(ScoringDimension):
    name = "engagement"
    weight = 0.10

    async def score(self, keyword, org_id, db) -> float:
        cpc = float(keyword.cpc or 0.0)
        return round(min(10.0, cpc * 0.8), 3)


DIMENSIONS: list[ScoringDimension] = [
    SearchPotentialDimension(),
    CompetitiveGapDimension(),
    TrendDimension(),
    EngagementDimension(),
]

_INTENT_MULTIPLIER = {
    "commercial": 1.5,
    "transactional": 1.3,
    "informational": 1.0,
    "navigational": 0.3,
}


async def compute_composite(keyword, org_id, db) -> dict:
    intent_multiplier = _INTENT_MULTIPLIER.get(
        str(keyword.intent or "informational").lower(), 1.0
    )

    scores = {}
    weighted_sum = 0.0
    for dim in DIMENSIONS:
        s = await dim.score(keyword, org_id, db)
        scores[dim.name] = s
        weighted_sum += s * dim.weight

    composite = round(weighted_sum * intent_multiplier, 3)

    return {
        "composite_score": composite,
        "search_score": scores["search_potential"],
        "competitive_gap_score": scores["competitive_gap"],
        "trend_score": scores["trend"],
        "engagement_score": scores["engagement"],
    }


# ── Agent ─────────────────────────────────────────────────────────────────────

@register
class OpportunityScorerAgent(BaseAgent):
    name = "opportunity_scorer"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        org_id = ctx.org_id
        keyword_ids = ctx.params.get("keyword_ids", [])

        if keyword_ids:
            where_clause = """
                k.status = 'validated'
                AND k.id = ANY(:keyword_ids)
                AND NOT EXISTS (
                    SELECT 1 FROM opportunities o WHERE o.keyword_id = k.id
                )
            """
            params = {"org_id": org_id, "keyword_ids": keyword_ids}
        else:
            where_clause = """
                k.status = 'validated'
                AND NOT EXISTS (
                    SELECT 1 FROM opportunities o WHERE o.keyword_id = k.id
                )
            """
            params = {"org_id": org_id}

        result = await ctx.db.execute(text(f"""
            SELECT k.id, k.keyword, k.volume, k.kd, k.cpc, k.intent
            FROM keywords k
            WHERE k.org_id = :org_id
              AND {where_clause}
            ORDER BY k.volume DESC
        """), params)

        keywords = result.fetchall()

        if not keywords:
            return AgentResult(
                status="success",
                data={
                    "opportunities_created": 0,
                    "message": "No unscored validated keywords found",
                },
                tokens_used=0,
                cost_usd=0.0,
            )

        created = 0
        top_keyword = None
        top_score = 0.0
        composite_scores = []

        for kw in keywords:
            scored = await compute_composite(kw, org_id, ctx.db)

            composite_scores.append(scored["composite_score"])
            if scored["composite_score"] > top_score:
                top_score = scored["composite_score"]
                top_keyword = kw.keyword

            output = OpportunityOutput(
                keyword_id=str(kw.id),
                org_id=org_id,
                **scored,
            )

            await ctx.db.execute(text("""
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
            """), {
                "org_id": org_id,
                "keyword_id": output.keyword_id,
                "source": output.source,
                "search_score": output.search_score,
                "gap_score": output.competitive_gap_score,
                "trend_score": output.trend_score,
                "engagement_score": output.engagement_score,
                "composite_score": output.composite_score,
            })
            created += 1

        await ctx.db.flush()

        return AgentResult(
            status="success",
            data={
                "opportunities_created": created,
                "top_opportunity": top_keyword,
                "score_range": {
                    "min": round(min(composite_scores), 2) if composite_scores else 0,
                    "max": round(max(composite_scores), 2) if composite_scores else 0,
                },
                "note": (
                    "competitive_gap and trend are 5.0 placeholders — "
                    "connect GSC and trend_collector for real values"
                ),
            },
            tokens_used=0,
            cost_usd=0.0,
        )
