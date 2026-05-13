"""content_director — orchestrates the full content pipeline for one opportunity.

Standard tier (minimal LLM — mostly orchestration).
  1. Calls article_planner → gets article_plan_id.
  2. Calls article_writer → gets article_id.
  3. Calls linkedin_agent, twitter_agent, newsletter_agent, video_scriptwriter.
  4. Returns IDs of all created content pieces.

Input params:
  opportunity_id (str, required)
"""
from __future__ import annotations

import logging

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import REGISTRY, register
from core.contracts import ContentDirectorOutput

logger = logging.getLogger(__name__)

_SUB_AGENTS = [
    ("article_planner", "opportunity_id"),
    ("article_writer", "article_plan_id"),
    ("linkedin_agent", "article_id"),
    ("twitter_agent", "article_id"),
    ("newsletter_agent", "article_id"),
    ("video_scriptwriter", "article_id"),
]


@register
class ContentDirectorAgent(BaseAgent):
    name = "content_director"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        opportunity_id = str(ctx.params.get("opportunity_id", "")).strip()
        if not opportunity_id:
            return AgentResult(status="failed", error="opportunity_id param is required")

        results: dict[str, str] = {}
        errors: list[str] = []

        # Stage A: article_planner
        plan_result = await _run_sub(ctx, "article_planner", {"opportunity_id": opportunity_id})
        if plan_result.status == "failed":
            errors.append(f"article_planner: {plan_result.error}")
        else:
            results["article_plan_id"] = plan_result.data.get("article_plan_id", "")

        # Stage B: article_writer (needs plan_id)
        article_id = ""
        if results.get("article_plan_id"):
            write_result = await _run_sub(
                ctx, "article_writer",
                {"article_plan_id": results["article_plan_id"]},
            )
            if write_result.status == "failed":
                errors.append(f"article_writer: {write_result.error}")
            else:
                article_id = write_result.data.get("article_id", "")
                results["article_id"] = article_id

        # Stage C: social agents
        # LinkedIn + Twitter read from article_plan (outline) — cheaper, faster
        # Newsletter reads from full article — needs depth
        # video_scriptwriter reads from full article — needs content
        plan_id = results.get("article_plan_id", "")

        for agent_name, param_key, param_val in [
            # LinkedIn + Twitter use plan outline → 70% fewer tokens
            ("linkedin_agent",    "article_plan_id", plan_id),
            ("twitter_agent",     "article_plan_id", plan_id),
            # Newsletter + video need full article for depth
            ("newsletter_agent",  "article_id",      article_id),
            ("video_scriptwriter","article_id",       article_id),
        ]:
            if not param_val:
                continue
            sub_result = await _run_sub(ctx, agent_name, {param_key: param_val})
            if sub_result.status == "failed":
                errors.append(f"{agent_name}: {sub_result.error}")
            else:
                id_keys = [k for k in sub_result.data if k.endswith("_id")]
                if id_keys:
                    results[id_keys[0]] = sub_result.data[id_keys[0]]

        output = ContentDirectorOutput(
            opportunity_id=opportunity_id,
            article_plan_id=results.get("article_plan_id", ""),
            article_id=results.get("article_id", ""),
            linkedin_post_id=results.get("linkedin_post_id", ""),
            twitter_thread_id=results.get("twitter_thread_id", ""),
            newsletter_id=results.get("newsletter_id", ""),
            video_script_id=results.get("video_script_id", ""),
            status="partial" if errors else "success",
        )
        return AgentResult(status="success", data=output.model_dump())


async def _run_sub(ctx: AgentContext, agent_name: str, params: dict) -> AgentResult:
    """Instantiate and run a sub-agent with the same DB/LLM context."""
    if agent_name not in REGISTRY:
        logger.warning("content_director: sub-agent '%s' not registered", agent_name)
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
        logger.exception("content_director: sub-agent %s failed", agent_name)
        return AgentResult(status="failed", error=str(exc))
