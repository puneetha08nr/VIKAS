"""content_extractor — fetches and extracts body text from competitor pages.

No LLM. Reads competitor_content rows where body IS NULL, fetches each URL
via ContentFetchIntegration, updates title/body/word_count/extracted_at.
"""
import logging

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import ContentExtractorOutput
from integrations.content_fetch import ContentFetchIntegration

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 100


@register
class ContentExtractorAgent(BaseAgent):
    name = "content_extractor"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        competitor_ids: list[str] = ctx.params.get("competitor_ids", [])
        limit: int = int(ctx.params.get("limit", _DEFAULT_LIMIT))

        rows = await _fetch_unextracted(ctx.org_id, competitor_ids, limit, ctx.db)
        if not rows:
            return AgentResult(
                status="success",
                data={
                    "total": 0,
                    "extracted": 0,
                    "failed": 0,
                    "skipped": 0,
                    "message": "No unextracted pages found",
                },
            )

        integration = ContentFetchIntegration()
        total = len(rows)
        extracted = failed = skipped = 0

        for row in rows:
            fetch_result = await integration.fetch_page(row.url)

            try:
                output = ContentExtractorOutput(
                    url=row.url,
                    domain=row.domain,
                    title=fetch_result.get("title", ""),
                    word_count=fetch_result.get("word_count", 0),
                    status=fetch_result.get("status", "failed"),
                )
            except ValidationError as exc:
                logger.warning("content_extractor: invalid result for %s: %s", row.url, exc)
                failed += 1
                continue

            if output.status == "ok":
                await _update_content(
                    content_id=row.id,
                    output=output,
                    body=fetch_result.get("body", ""),
                    db=ctx.db,
                )
                extracted += 1
            elif output.status == "skipped":
                skipped += 1
            else:
                failed += 1

        await ctx.db.flush()

        return AgentResult(
            status="success",
            data={"total": total, "extracted": extracted, "failed": failed, "skipped": skipped},
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_unextracted(
    org_id: str,
    competitor_ids: list[str],
    limit: int,
    db: AsyncSession,
) -> list:
    if competitor_ids:
        placeholders, id_params = _in_clause(competitor_ids)
        filter_sql = f"AND cc.competitor_id IN ({placeholders})"
    else:
        id_params = {}
        filter_sql = ""

    result = await db.execute(
        text(
            f"""
            SELECT cc.id, cc.url, c.domain
            FROM competitor_content cc
            JOIN competitors c ON cc.competitor_id = c.id
            WHERE cc.org_id = :org_id
              AND cc.body IS NULL
              {filter_sql}
            ORDER BY cc.created_at
            LIMIT :limit
            """
        ),
        {"org_id": org_id, "limit": limit, **id_params},
    )
    return result.fetchall()


async def _update_content(
    content_id: str,
    output: ContentExtractorOutput,
    body: str,
    db: AsyncSession,
) -> None:
    await db.execute(
        text(
            "UPDATE competitor_content SET "
            "title = COALESCE(NULLIF(:title, ''), title), "
            "word_count = :word_count, "
            "body = :body, "
            "extracted_at = now() "
            "WHERE id = :id"
        ),
        {
            "id": content_id,
            "title": output.title,
            "word_count": output.word_count,
            "body": body,
        },
    )


def _in_clause(ids: list[str]) -> tuple[str, dict[str, str]]:
    placeholders = ", ".join(f":cid_{i}" for i in range(len(ids)))
    params = {f"cid_{i}": str(id_) for i, id_ in enumerate(ids)}
    return placeholders, params
