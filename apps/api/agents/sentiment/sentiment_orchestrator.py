"""sentiment.sentiment_orchestrator — chains Stages 2-4 of the sentiment pipeline.

Stage 1 (collectors) are triggered separately per source type. This agent
orchestrates everything from filtering through to spike analysis:

  Stage 2  → sentiment_filter
  Stage 3a → sentiment_polarity_classifier
  Stage 3b → sentiment_theme_tagger
  Stage 3c → sentiment_entity_extractor
  Stage 4a → sentiment_aggregator
  Stage 4b → sentiment_spike_detector

Each stage runs even if an upstream stage failed — stages operate on
distinct status values so a partial upstream result still produces useful
downstream output. Stage failure is isolated: the pipeline never aborts.

Input params:
  scheme_key        (str, default "")
  district_key      (str, default "")
  signal_date       (str, default "") — ISO date for aggregator; "" = yesterday
  filter_batch      (int, default 200)
  polarity_batch    (int, default 100)
  theme_batch       (int, default 200)
  entity_batch      (int, default 200)
  spike_batch       (int, default 20)
  vader_threshold   (float, default 0.85)
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import REGISTRY, register

logger = logging.getLogger(__name__)

_PIPELINE_NAME = "sentiment_pipeline"

# Ordered stages: (agent_name, param_builder_key)
_STAGES: list[tuple[str, str]] = [
    ("sentiment_filter",                "filter"),
    ("sentiment_polarity_classifier",   "polarity"),
    ("sentiment_theme_tagger",          "theme"),
    ("sentiment_entity_extractor",      "entity"),
    ("sentiment_aggregator",            "aggregator"),
    ("sentiment_spike_detector",        "spike"),
]


@register
class SentimentOrchestratorAgent(BaseAgent):
    name = "sentiment_orchestrator"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        district_key: str = ctx.params.get("district_key", "")
        signal_date: str = ctx.params.get("signal_date", "")

        stage_params = _build_stage_params(ctx.params, scheme_key, district_key, signal_date)
        pipeline_run_id = str(uuid.uuid4())

        await _create_pipeline_run(pipeline_run_id, ctx)

        stage_results: dict[str, Any] = {}
        stages_ok = 0
        stages_failed = 0

        for agent_name, param_key in _STAGES:
            params = stage_params.get(param_key, {})
            result = await _run_sub(ctx, agent_name, params)
            stage_results[agent_name] = {
                "status": result.status,
                "data": result.data,
                "error": result.error,
            }
            if result.status == "success":
                stages_ok += 1
                logger.info(
                    "sentiment_orchestrator: %s succeeded — %s",
                    agent_name, result.data,
                )
            else:
                stages_failed += 1
                logger.warning(
                    "sentiment_orchestrator: %s failed — %s",
                    agent_name, result.error,
                )

        overall_status = (
            "failed" if stages_ok == 0 else
            "partial" if stages_failed > 0 else
            "success"
        )

        await _update_pipeline_run(pipeline_run_id, overall_status, ctx)

        logger.info(
            "sentiment_orchestrator: pipeline=%s ok=%d failed=%d scheme=%s",
            overall_status, stages_ok, stages_failed, scheme_key or "(all)",
        )
        return AgentResult(
            status=overall_status,
            data={
                "pipeline_run_id": pipeline_run_id,
                "stages_succeeded": stages_ok,
                "stages_failed": stages_failed,
                "scheme_key": scheme_key,
                "district_key": district_key,
                "stages": stage_results,
            },
        )


# ── Stage param construction ──────────────────────────────────────────────────

def _build_stage_params(
    raw: dict[str, Any],
    scheme_key: str,
    district_key: str,
    signal_date: str,
) -> dict[str, dict[str, Any]]:
    base = {"scheme_key": scheme_key, "district_key": district_key}
    return {
        "filter": {
            **base,
            "batch_size": int(raw.get("filter_batch", 200)),
        },
        "polarity": {
            **base,
            "batch_size": int(raw.get("polarity_batch", 100)),
            "vader_threshold": float(raw.get("vader_threshold", 0.85)),
        },
        "theme": {
            **base,
            "batch_size": int(raw.get("theme_batch", 200)),
        },
        "entity": {
            **base,
            "batch_size": int(raw.get("entity_batch", 200)),
        },
        "aggregator": {
            **base,
            "signal_date": signal_date,
            "window_hours": int(raw.get("window_hours", 24)),
        },
        "spike": {
            **base,
            "batch_size": int(raw.get("spike_batch", 20)),
        },
    }


# ── Sub-agent runner ──────────────────────────────────────────────────────────

async def _run_sub(
    ctx: AgentContext,
    agent_name: str,
    params: dict[str, Any],
) -> AgentResult:
    if agent_name not in REGISTRY:
        return AgentResult(status="failed", error=f"{agent_name} not registered")
    sub_ctx = AgentContext(
        org_id=ctx.org_id,
        run_id=ctx.run_id,
        params=params,
        config=ctx.config,
        db=ctx.db,
        llm=ctx.llm,
    )
    try:
        return await REGISTRY[agent_name]().execute(sub_ctx)
    except Exception as exc:
        logger.exception(
            "sentiment_orchestrator: sub-agent %s raised unhandled exception", agent_name
        )
        return AgentResult(status="failed", error=str(exc))


# ── Pipeline run logging ──────────────────────────────────────────────────────

async def _create_pipeline_run(pipeline_run_id: str, ctx: AgentContext) -> None:
    await ctx.db.execute(
        text(
            "INSERT INTO pipeline_runs "
            "  (id, org_id, pipeline_name, status, started_at, completed_at) "
            "VALUES "
            "  (CAST(:id AS uuid), :org_id, :pipeline_name, 'running', now(), now())"
        ),
        {
            "id": pipeline_run_id,
            "org_id": ctx.org_id,
            "pipeline_name": _PIPELINE_NAME,
        },
    )
    await ctx.db.flush()


async def _update_pipeline_run(
    pipeline_run_id: str, status: str, ctx: AgentContext
) -> None:
    await ctx.db.execute(
        text(
            "UPDATE pipeline_runs "
            "SET status = :status, completed_at = now() "
            "WHERE id = CAST(:id AS uuid)"
        ),
        {"id": pipeline_run_id, "status": status},
    )
    await ctx.db.flush()
