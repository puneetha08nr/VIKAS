"""
video_script_agent — Turns a finished article into a video script with scenes.

Reads the video_script content_item stub, finds the article from the same
opportunity, then calls the LLM (standard tier) to produce a structured script
with narration, visuals, b-roll notes, and durations per scene.
"""
import json
import logging
import re
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import VideoScriptOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

_DEFAULT_DURATION = 180  # seconds


@register
class VideoScriptAgent(BaseAgent):
    name = "video_script_agent"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        content_item_id = ctx.params.get("content_item_id", "").strip()
        if not content_item_id:
            return AgentResult(status="failed", error="content_item_id param is required")

        item = await _fetch_content_item(content_item_id, ctx.org_id, ctx.db)
        if item is None:
            return AgentResult(status="failed", error=f"content_item {content_item_id} not found for this org")

        if item["format"] != "video_script":
            return AgentResult(status="failed", error=f"video_script_agent only handles format=video_script, got {item['format']}")

        keyword = item["keyword"]
        article_body = await _fetch_article_body(item["opportunity_id"], ctx.org_id, ctx.db)
        source_content = _truncate(article_body, 3000) if article_body else f"Topic: {keyword}."

        target_duration = int(ctx.params.get("target_duration", _DEFAULT_DURATION))
        prompt_template = await PromptRegistry().get(self.name, ctx.db)
        prompt = (
            prompt_template
            .replace("SOURCE_CONTENT", source_content)
            .replace("PRIMARY_KEYWORD", keyword)
            .replace("TARGET_DURATION", str(target_duration))
        )

        raw_response = await self.call_llm(ctx, prompt)
        logger.info("[video_script_agent] raw LLM response:\n%s\n", raw_response[:300])

        parsed = _parse_script(raw_response)
        if parsed is None:
            return AgentResult(status="failed", error="LLM returned unparseable script JSON — check logs for raw response")

        try:
            output = VideoScriptOutput(
                content_item_id=content_item_id,
                title=parsed.get("title", item["title"]),
                total_duration_seconds=parsed.get("total_duration_seconds", target_duration),
                scenes=parsed.get("scenes", []),
                cta=parsed.get("cta", ""),
            )
        except ValidationError as exc:
            return AgentResult(status="failed", error=f"script failed contract validation: {exc}")

        if not output.scenes:
            return AgentResult(status="failed", error="LLM returned empty scenes list")

        script_body = json.dumps({
            "title": output.title,
            "total_duration_seconds": output.total_duration_seconds,
            "scenes": output.scenes,
            "cta": output.cta,
        }, ensure_ascii=False)

        await _write_item(content_item_id, output.title, script_body, ctx.db)
        await ctx.db.flush()

        return AgentResult(
            status="success",
            data={
                "content_item_id": content_item_id,
                "keyword": keyword,
                "title": output.title,
                "scene_count": len(output.scenes),
                "total_duration_seconds": output.total_duration_seconds,
                "source": "article" if article_body else "keyword_only",
            },
            tokens_used=ctx.llm.last_tokens_used,
            cost_usd=ctx.llm.last_cost_usd,
        )


async def _fetch_content_item(content_item_id: str, org_id: str, db: AsyncSession) -> dict[str, Any] | None:
    result = await db.execute(
        text("""
            SELECT ci.id, ci.format, ci.title, ci.opportunity_id, k.keyword
            FROM content_items ci
            JOIN opportunities o ON ci.opportunity_id = o.id
            JOIN keywords k ON o.keyword_id = k.id
            WHERE ci.id = :id AND ci.org_id = :org_id
        """),
        {"id": content_item_id, "org_id": org_id},
    )
    row = result.fetchone()
    if row is None:
        return None
    return {"id": str(row[0]), "format": str(row[1]), "title": str(row[2]), "opportunity_id": str(row[3]), "keyword": str(row[4])}


async def _fetch_article_body(opportunity_id: str, org_id: str, db: AsyncSession) -> str:
    result = await db.execute(
        text("""
            SELECT body FROM content_items
            WHERE opportunity_id = :opp_id AND org_id = :org_id
              AND format = 'article' AND status IN ('draft', 'approved', 'published') AND body != ''
            LIMIT 1
        """),
        {"opp_id": opportunity_id, "org_id": org_id},
    )
    row = result.fetchone()
    return str(row[0]) if row and row[0] else ""


async def _write_item(content_item_id: str, title: str, body: str, db: AsyncSession) -> None:
    await db.execute(
        text("UPDATE content_items SET title=:title, body=:body, status='draft', updated_at=now() WHERE id=:id"),
        {"id": content_item_id, "title": title, "body": body},
    )


def _parse_script(response: str) -> dict[str, Any] | None:
    if not response or not response.strip():
        return None
    cleaned = re.sub(r"```(?:json)?", "", response, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    if cleaned.startswith("{"):
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict) and "scenes" in data:
                return data
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass
    return None


def _truncate(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars] + "... [truncated]"
