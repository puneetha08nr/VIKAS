"""competitor_discovery — discovers competitor domains for a seed keyword.

Fast tier LLM (data analysis, no long-form writing).
Reads from keywords table, writes to competitors table.

Input params:
  keyword (str, required) — seed keyword to find competitors for
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import CompetitorDiscoveryOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


@register
class CompetitorDiscoveryAgent(BaseAgent):
    name = "competitor_discovery"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        keyword = str(ctx.params.get("keyword", "")).strip()
        if not keyword:
            return AgentResult(status="failed", error="keyword param is required")

        template = await PromptRegistry().get(self.name, ctx.db)
        prompt = template.replace("KEYWORD", keyword)

        raw = await self.call_llm(ctx, prompt)
        domains = _parse_domains(raw)

        written = 0
        for domain in domains:
            if not domain:
                continue
            try:
                await ctx.db.execute(
                    text(
                        "INSERT INTO competitors (id, org_id, domain, last_crawled_at) "
                        "VALUES (gen_random_uuid(), :org_id, :domain, NULL) "
                        "ON CONFLICT (org_id, domain) DO NOTHING"
                    ),
                    {"org_id": ctx.org_id, "domain": domain},
                )
                written += 1
            except Exception:
                logger.warning("competitor_discovery: failed to insert domain %s", domain)

        await ctx.db.flush()

        output = CompetitorDiscoveryOutput(
            seed_keyword=keyword,
            competitors_found=len(domains),
            competitors_written=written,
        )
        return AgentResult(status="success", data=output.model_dump())


def _parse_domains(raw: str) -> list[str]:
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```")
        parsed = json.loads(clean)
        if isinstance(parsed, list):
            return [
                str(d.get("domain", d) if isinstance(d, dict) else d).strip()
                for d in parsed
                if d
            ]
    except Exception:
        pass
    # Fallback: one domain per line
    return [ln.strip().lower() for ln in raw.splitlines() if ln.strip() and "." in ln]
