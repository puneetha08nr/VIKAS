"""competitor_monitor — crawls competitor sitemaps and upserts to competitors table.

No LLM. Uses SitemapIntegration (BaseIntegration subclass) so all HTTP calls
go through the circuit-breaker and rate-limiter. Writes one row per domain to
the competitors table with last_crawled_at updated on each run.
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import CompetitorMonitorOutput
from integrations.base import IntegrationError
from integrations.sitemap import SitemapIntegration

logger = logging.getLogger(__name__)


@register
class CompetitorMonitorAgent(BaseAgent):
    name = "competitor_monitor"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        domains: list[str] = ctx.params.get("competitors", [])

        # Fall back to domains already stored for this org
        if not domains:
            domains = await _fetch_stored_domains(ctx.org_id, ctx.db)

        if not domains:
            return AgentResult(
                status="success",
                data={
                    "competitors_monitored": 0,
                    "total": 0,
                    "results": [],
                    "message": (
                        "No competitor domains found. "
                        "Pass 'competitors' param or seed the competitors table."
                    ),
                },
            )

        integration = SitemapIntegration()
        results: list[dict] = []

        for domain in domains:
            entry: dict = {"domain": domain, "urls_found": 0, "status": "ok"}
            try:
                urls = await integration.fetch_sitemap(domain)
                entry["urls_found"] = len(urls)
                await _upsert_competitor(ctx.org_id, domain, ctx.db)
            except IntegrationError as exc:
                logger.warning("competitor_monitor: %s unreachable: %s", domain, exc)
                entry["status"] = "unreachable"
                await _ensure_competitor(ctx.org_id, domain, ctx.db)

            output = CompetitorMonitorOutput(**entry)
            results.append(output.model_dump())

        await ctx.db.flush()

        ok_count = sum(1 for r in results if r["status"] == "ok")
        overall = "success" if ok_count == len(domains) else "partial"

        return AgentResult(
            status=overall,
            data={
                "competitors_monitored": ok_count,
                "total": len(domains),
                "results": results,
            },
        )


async def _upsert_competitor(org_id: str, domain: str, db: AsyncSession) -> None:
    """Insert or update a competitor row. Updates last_crawled_at on conflict."""
    await db.execute(
        text(
            "INSERT INTO competitors (id, org_id, domain, last_crawled_at, created_at) "
            "VALUES (gen_random_uuid(), :org_id, :domain, now(), now()) "
            "ON CONFLICT (org_id, domain) DO UPDATE SET last_crawled_at = now()"
        ),
        {"org_id": org_id, "domain": domain},
    )


async def _ensure_competitor(org_id: str, domain: str, db: AsyncSession) -> None:
    """Insert a competitor row without setting last_crawled_at (unreachable domain)."""
    await db.execute(
        text(
            "INSERT INTO competitors (id, org_id, domain, created_at) "
            "VALUES (gen_random_uuid(), :org_id, :domain, now()) "
            "ON CONFLICT (org_id, domain) DO NOTHING"
        ),
        {"org_id": org_id, "domain": domain},
    )


async def _fetch_stored_domains(org_id: str, db: AsyncSession) -> list[str]:
    """Return all competitor domains already in the DB for this org."""
    result = await db.execute(
        text(
            "SELECT domain FROM competitors "
            "WHERE org_id = :org_id "
            "ORDER BY last_crawled_at ASC NULLS FIRST"
        ),
        {"org_id": org_id},
    )
    return [row[0] for row in result.fetchall()]
