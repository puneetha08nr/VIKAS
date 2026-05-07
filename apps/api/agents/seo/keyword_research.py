"""
keyword_research — SEO data provider driven, no LLM.

Metric sourcing (tiered — first success wins):
  Tier 1: DataForSEO keywords ideas (Google Suggest + real metrics)
  Tier 2: Keywords Everywhere (not yet built — skipped)
  Tier 3: Anchor-Scale Estimator (DB anchors + PyTrends + Suggest count)
  Tier 4: Pending (save with null metrics, true-up via /fetch-metrics)

Design principle: pipeline never stops, confidence degrades gracefully.
"""
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from integrations.anchor_scale_estimator import AnchorScaleEstimator
from integrations.dataforseo import DataForSEOIntegration, _get_google_suggestions, _infer_intent

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

        # ── Tier 1: DataForSEO ideas (Google Suggest + real metrics) ─────────
        try:
            raw_keywords = await DataForSEOIntegration().get_keyword_ideas(
                seed=seed,
                org_id=org_id,
                db=ctx.db,
            )
            for kw in raw_keywords:
                kw.setdefault("data_source", "dataforseo")
        except Exception as exc:
            logger.warning(
                "keyword_research: Tier 1 DataForSEO failed (%s: %s)"
                " — falling through to Tiers 2-4",
                type(exc).__name__, exc,
            )
            suggestions = await _get_google_suggestions(seed) or [seed]
            kw_texts = suggestions[:20]
            raw_keywords = await _get_metrics(kw_texts, seed, ctx)

        if not raw_keywords:
            return AgentResult(
                status="partial",
                data={"keywords_found": 0, "seed": seed},
                tokens_used=0,
                cost_usd=0.0,
                error="No keyword ideas produced — all metric sources failed",
            )

        # ── Cluster by intent (pure Python) ──────────────────────────────────
        clusters = _cluster_by_intent(raw_keywords)

        # ── Write clusters + keywords to DB ───────────────────────────────────
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

        # ── Priority score ────────────────────────────────────────────────────
        await _score_keywords(org_id=org_id, run_id=ctx.run_id, db=ctx.db)

        # Summarise data_source for result (most common among saved keywords)
        ds_counts: dict[str, int] = {}
        for kw in raw_keywords:
            ds = kw.get("data_source", "pending")
            ds_counts[ds] = ds_counts.get(ds, 0) + 1
        primary_ds = max(ds_counts, key=lambda k: ds_counts[k]) if ds_counts else "pending"

        return AgentResult(
            status="success" if total_saved > 0 else "partial",
            data={
                "keywords_found": total_saved,
                "seed": seed,
                "clusters": {k: len(v) for k, v in clusters.items()},
                "data_source": primary_ds,
            },
            tokens_used=0,
            cost_usd=0.0,
        )


# ── Tiered metric sourcing ────────────────────────────────────────────────────

async def _get_metrics(
    keywords: list[str], seed: str, ctx: AgentContext
) -> list[dict]:
    """Get metrics for keyword texts. Tries Tiers 2-4 in order."""

    # Tier 2 — Keywords Everywhere (not yet built)

    # Tier 3 — Anchor-Scale Estimator
    try:
        estimates = await AnchorScaleEstimator().estimate_metrics(
            keywords, seed, ctx.db
        )
        if estimates:
            return [
                {
                    "keyword": e["keyword"],
                    "volume": e.get("volume"),
                    "kd": e.get("kd"),
                    "cpc": e.get("cpc"),
                    "intent": _infer_intent(e["keyword"]),
                    "data_source": e.get("data_source", "pending"),
                }
                for e in estimates
            ]
    except Exception as exc:
        logger.warning("keyword_research: Tier 3 Anchor-Scale failed: %s", exc)

    # Tier 4 — Pending (never fails)
    logger.warning(
        "keyword_research: All metric sources failed for seed '%s'"
        " — saving %d keywords as pending.",
        seed, len(keywords),
    )
    return [
        {
            "keyword": kw,
            "volume": None,
            "kd": None,
            "cpc": None,
            "intent": _infer_intent(kw),
            "data_source": "pending",
        }
        for kw in keywords
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cluster_by_intent(keywords: list[dict]) -> dict[str, list[dict]]:
    clusters: dict[str, list[dict]] = {}
    for kw in keywords:
        intent = (kw.get("intent") or "informational").lower().strip()
        clusters.setdefault(intent, []).append(kw)
    return {k: v for k, v in clusters.items() if v}


def _priority_score(volume: int, kd: float, intent: str) -> float:
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
    """Insert keywords. Reads data_source from each keyword dict."""
    saved = 0
    for kw in keywords:
        keyword_text = str(kw.get("keyword") or "").strip()
        if not keyword_text:
            continue

        volume = int(kw["volume"]) if kw.get("volume") is not None else None
        kd = float(kw["kd"]) if kw.get("kd") is not None else None
        cpc = float(kw["cpc"]) if kw.get("cpc") is not None else None
        intent = str(kw.get("intent") or "informational").lower().strip()
        data_source = str(kw.get("data_source") or "pending")
        priority = (
            _priority_score(volume, kd, intent)
            if volume is not None and kd is not None
            else None
        )

        result = await db.execute(
            text(
                "INSERT INTO keywords "
                "(id, org_id, keyword, volume, kd, cpc, intent, "
                " cluster_id, status, source_agent, source_run_id, "
                " data_source, priority_score, created_at, updated_at) "
                "VALUES "
                "(gen_random_uuid(), :org_id, :keyword, :volume, :kd, :cpc, "
                " :intent, :cluster_id, 'raw', :source_agent, :source_run_id, "
                " :data_source, :priority_score, now(), now()) "
                "ON CONFLICT (org_id, keyword) DO NOTHING "
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
                "data_source": data_source,
                "priority_score": priority,
            },
        )
        if result.fetchone() is not None:
            saved += 1

    await db.flush()
    return saved


async def _score_keywords(org_id: str, run_id: str, db: AsyncSession) -> None:
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
