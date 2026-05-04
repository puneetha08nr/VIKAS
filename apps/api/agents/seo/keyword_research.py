"""
keyword_research — SEO data provider driven, no LLM.

Primary source: DataForSEO Keywords Ideas API
Clustering:     Pure Python by intent
Scoring:        Pure Python composite formula
"""
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from integrations.base import IntegrationError
from integrations.dataforseo import DataForSEOIntegration

logger = logging.getLogger(__name__)


@register
class KeywordResearchAgent(BaseAgent):
    name = "keyword_research"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        seed = ctx.params.get("seed_keyword", "").strip()
        if not seed:
            return AgentResult(
                status="failed",
                data={},
                tokens_used=0,
                cost_usd=0.0,
                error="seed_keyword param is required",
            )

        org_id = ctx.org_id

        # ── Step 1: Fetch keyword ideas from DataForSEO ──────────────────────
        integration = DataForSEOIntegration()

        try:
            raw_keywords = await integration.get_keyword_ideas(
                seed=seed,
                org_id=org_id,
                db=ctx.db,
            )
        except IntegrationError as e:
            logger.error("keyword_research: DataForSEO failed: %s", e)
            return AgentResult(
                status="failed",
                data={},
                tokens_used=0,
                cost_usd=0.0,
                error=(
                    "DataForSEO credentials not configured or API call failed. "
                    "Add DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD in "
                    "Settings → Integrations. "
                    f"Detail: {e}"
                ),
            )

        if not raw_keywords:
            return AgentResult(
                status="partial",
                data={"keywords_found": 0, "seed": seed},
                tokens_used=0,
                cost_usd=0.0,
                error="DataForSEO returned no keyword ideas for this seed",
            )

        # ── Step 2: Cluster by intent (pure Python) ───────────────────────────
        clusters = _cluster_by_intent(raw_keywords)
        # e.g. {"commercial": [...], "informational": [...]}

        # ── Step 3: Write clusters + keywords to DB ───────────────────────────
        total_saved = 0
        for intent, keywords in clusters.items():
            if not keywords:
                continue

            cluster_id = await _create_cluster(
                org_id=org_id,
                name=f"{seed} — {intent}",
                intent=intent,
                db=ctx.db,
            )

            saved = await _save_keywords(
                keywords=keywords,
                org_id=org_id,
                cluster_id=cluster_id,
                source_agent=self.name,
                source_run_id=ctx.run_id,
                db=ctx.db,
            )
            total_saved += saved

        # ── Step 4: Priority score (pure Python) ──────────────────────────────
        await _score_keywords(org_id=org_id, run_id=ctx.run_id, db=ctx.db)

        return AgentResult(
            status="success",
            data={
                "keywords_found": total_saved,
                "seed": seed,
                "clusters": {k: len(v) for k, v in clusters.items()},
                "data_source": "dataforseo",
            },
            tokens_used=0,
            cost_usd=0.0,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cluster_by_intent(keywords: list[dict]) -> dict[str, list[dict]]:
    """Group keywords by intent field. No LLM."""
    clusters: dict[str, list[dict]] = {}
    for kw in keywords:
        intent = (kw.get("intent") or "informational").lower().strip()
        clusters.setdefault(intent, []).append(kw)
    # return only non-empty buckets
    return {k: v for k, v in clusters.items() if v}


def _priority_score(volume: int, kd: float, intent: str) -> float:
    """
    Composite priority score — pure arithmetic.
    Higher = more worth targeting.

    Formula: (volume / 1000) * (10 - kd) * intent_multiplier
    """
    multiplier = 2.0 if intent in ("commercial", "transactional") else 1.0
    return round((volume / 1000) * max(0.0, 10.0 - kd) * multiplier, 3)


async def _create_cluster(
    org_id: str,
    name: str,
    intent: str,
    db: AsyncSession,
) -> str:
    cluster_id = str(uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO keyword_clusters "
            "(id, org_id, name, intent, created_at) "
            "VALUES (:id, :org_id, :name, :intent, now()) "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": cluster_id, "org_id": org_id, "name": name, "intent": intent},
    )
    return cluster_id


async def _save_keywords(
    keywords: list[dict],
    org_id: str,
    cluster_id: str,
    source_agent: str,
    source_run_id: str,
    db: AsyncSession,
) -> int:
    """Insert keywords. Returns count of rows actually inserted."""
    saved = 0
    for kw in keywords:
        keyword_text = str(kw.get("keyword") or "").strip()
        if not keyword_text:
            continue

        volume = int(kw.get("volume") or 0)
        kd = float(kw.get("kd") or 0.0)
        cpc = float(kw.get("cpc") or 0.0)
        intent = str(kw.get("intent") or "informational").lower().strip()
        priority = _priority_score(volume, kd, intent)

        result = await db.execute(
            text(
                "INSERT INTO keywords "
                "(id, org_id, keyword, volume, kd, cpc, intent, "
                " cluster_id, status, source_agent, source_run_id, "
                " data_source, priority_score, created_at, updated_at) "
                "VALUES "
                "(gen_random_uuid(), :org_id, :keyword, :volume, :kd, :cpc, "
                " :intent, :cluster_id, 'raw', :source_agent, :source_run_id, "
                " 'dataforseo', :priority_score, now(), now()) "
                "ON CONFLICT DO NOTHING "
                "RETURNING id"
            ),
            {
                "org_id": org_id,
                "keyword": keyword_text,
                "volume": volume,
                "kd": kd,
                "cpc": cpc,
                "intent": intent,
                "cluster_id": cluster_id,
                "source_agent": source_agent,
                "source_run_id": source_run_id,
                "priority_score": priority,
            },
        )
        if result.fetchone() is not None:
            saved += 1

    await db.flush()
    return saved


async def _score_keywords(org_id: str, run_id: str, db: AsyncSession) -> None:
    """
    Update priority_score for keywords from this run.
    Already set during insert — this pass updates any that
    were skipped due to ON CONFLICT (existing rows).
    """
    await db.execute(
        text(
            "UPDATE keywords "
            "SET priority_score = "
            "  ROUND("
            "    ((volume::numeric / 1000) "
            "    * GREATEST(0, 10 - kd::numeric) "
            "    * CASE WHEN intent IN ('commercial','transactional') "
            "           THEN 2.0 ELSE 1.0 END)::numeric, "
            "  3) "
            "WHERE org_id = :org_id "
            "  AND source_run_id = :run_id "
            "  AND priority_score IS NULL"
        ),
        {"org_id": org_id, "run_id": run_id},
    )