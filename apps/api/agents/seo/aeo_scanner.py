"""aeo_scanner — checks whether org's keywords appear in Google SERP features.

AEO = Answer Engine Optimization. For each keyword the agent:
  1. Calls SerpScraperIntegration.scrape_serp() to fetch and parse the SERP.
  2. Classifies the result (AI Overview, Featured Snippet, PAA count,
     organic position) — no LLM required, pure HTML parsing.
  3. Upserts the result to aeo_results table.

Inputs:
  keyword_ids  (list[str], optional) — UUIDs to scan; defaults to all validated keywords
  domain       (str, optional)       — org's domain for organic_position lookup
  batch_size   (int, optional)       — keywords per run, default 10 (rate limit protection)

Output:
  total, ai_overview_count, featured_snippet_count, blocked_count
"""
import asyncio
import logging

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import AeoScannerOutput
from integrations.serp_scraper import SerpScraperIntegration

logger = logging.getLogger(__name__)

_DEFAULT_BATCH = 10
_INTER_KEYWORD_DELAY = 3.0   # seconds between keyword scrapes


@register
class AeoScannerAgent(BaseAgent):
    name = "aeo_scanner"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        keyword_ids: list[str] = ctx.params.get("keyword_ids") or []
        domain: str | None = ctx.params.get("domain") or None
        batch_size = max(1, int(ctx.params.get("batch_size", _DEFAULT_BATCH)))

        # ── Step 1: Resolve keywords ──────────────────────────────────────────
        if keyword_ids:
            kw_rows = await _fetch_keywords_by_ids(keyword_ids, ctx.org_id, ctx.db)
        else:
            kw_rows = await _fetch_validated_keywords(ctx.org_id, ctx.db, limit=batch_size)

        if not kw_rows:
            return AgentResult(
                status="success",
                data={
                    "total": 0,
                    "ai_overview_count": 0,
                    "featured_snippet_count": 0,
                    "blocked_count": 0,
                    "message": "No keywords to scan",
                },
            )

        # Cap to batch_size
        kw_rows = kw_rows[:batch_size]

        # ── Step 2: Scrape + classify ─────────────────────────────────────────
        scraper = SerpScraperIntegration()

        total = 0
        ai_overview_count = 0
        featured_snippet_count = 0
        blocked_count = 0

        for i, row in enumerate(kw_rows):
            keyword_id = str(row[0])
            keyword = str(row[1])

            if i > 0:
                await asyncio.sleep(_INTER_KEYWORD_DELAY)

            serp = await scraper.scrape_serp(keyword, domain=domain)

            if serp.get("blocked"):
                status = "blocked"
                blocked_count += 1
            elif serp.get("found"):
                status = "found"
            else:
                status = "not_found"

            raw = {
                "keyword_id": keyword_id,
                "keyword": keyword,
                "ai_overview": serp.get("ai_overview", False),
                "featured_snippet": serp.get("featured_snippet", False),
                "paa_count": serp.get("paa_count", 0),
                "organic_position": serp.get("organic_position"),
                "status": status,
            }

            try:
                output = AeoScannerOutput(**raw)
            except ValidationError as exc:
                logger.warning("aeo_scanner: validation error for %r: %s", keyword, exc)
                continue

            await _upsert_result(output, ctx.org_id, ctx.db)
            total += 1

            if output.ai_overview:
                ai_overview_count += 1
            if output.featured_snippet:
                featured_snippet_count += 1

        await ctx.db.flush()

        return AgentResult(
            status="success",
            data={
                "total": total,
                "ai_overview_count": ai_overview_count,
                "featured_snippet_count": featured_snippet_count,
                "blocked_count": blocked_count,
            },
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_validated_keywords(
    org_id: str, db: AsyncSession, limit: int
) -> list:
    result = await db.execute(
        text(
            "SELECT id, keyword FROM keywords "
            "WHERE org_id = :org_id AND status = 'validated' "
            "ORDER BY volume DESC NULLS LAST "
            "LIMIT :limit"
        ),
        {"org_id": org_id, "limit": limit},
    )
    return list(result.fetchall())


async def _fetch_keywords_by_ids(
    keyword_ids: list[str], org_id: str, db: AsyncSession
) -> list:
    result = await db.execute(
        text(
            "SELECT id, keyword FROM keywords "
            "WHERE org_id = :org_id AND id = ANY(CAST(:ids AS uuid[])) "
            "ORDER BY volume DESC NULLS LAST"
        ),
        {"org_id": org_id, "ids": keyword_ids},
    )
    return list(result.fetchall())


async def _upsert_result(
    output: AeoScannerOutput,
    org_id: str,
    db: AsyncSession,
) -> None:
    await db.execute(
        text(
            "INSERT INTO aeo_results "
            "  (id, org_id, keyword_id, keyword, ai_overview, featured_snippet, "
            "   paa_count, organic_position, status, scanned_at) "
            "VALUES "
            "  (gen_random_uuid(), :org_id, CAST(:keyword_id AS uuid), :keyword, "
            "   :ai_overview, :featured_snippet, :paa_count, :organic_position, "
            "   :status, now()) "
            "ON CONFLICT (keyword_id, org_id) DO UPDATE SET "
            "  ai_overview = EXCLUDED.ai_overview, "
            "  featured_snippet = EXCLUDED.featured_snippet, "
            "  paa_count = EXCLUDED.paa_count, "
            "  organic_position = EXCLUDED.organic_position, "
            "  status = EXCLUDED.status, "
            "  scanned_at = now(), "
            "  updated_at = now()"
        ),
        {
            "org_id": org_id,
            "keyword_id": output.keyword_id,
            "keyword": output.keyword,
            "ai_overview": output.ai_overview,
            "featured_snippet": output.featured_snippet,
            "paa_count": output.paa_count,
            "organic_position": output.organic_position,
            "status": output.status,
        },
    )
