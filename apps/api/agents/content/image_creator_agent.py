"""
image_creator_agent — Generates image prompts and optionally calls DALL-E 3.

Two-step process:
  Step 1: Standard LLM generates a detailed DALL-E prompt from article content
  Step 2: If OPENAI_API_KEY is set, calls openai.images.generate() (DALL-E 3)
          Otherwise saves the prompt only — image can be generated later

Stores result as JSON in content_items.body with prompt + image_url (if generated).
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
from core.contracts import ImageCreatorOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)

_DEFAULT_USE_CASE = "blog featured image"


@register
class ImageCreatorAgent(BaseAgent):
    name = "image_creator_agent"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        content_item_id = ctx.params.get("content_item_id", "").strip()
        if not content_item_id:
            return AgentResult(status="failed", error="content_item_id param is required")

        item = await _fetch_content_item(content_item_id, ctx.org_id, ctx.db)
        if item is None:
            return AgentResult(status="failed", error=f"content_item {content_item_id} not found for this org")

        if item["format"] != "article":
            return AgentResult(status="failed", error=f"image_creator_agent handles format=article items, got {item['format']}")

        keyword = item["keyword"]
        use_case = str(ctx.params.get("image_use_case", _DEFAULT_USE_CASE))

        # ── Step 1: Generate image prompt via standard LLM ───────────────────
        prompt_template = await PromptRegistry().get(self.name, ctx.db)
        prompt = (
            prompt_template
            .replace("ARTICLE_TITLE", item["title"])
            .replace("PRIMARY_KEYWORD", keyword)
            .replace("IMAGE_USE_CASE", use_case)
        )

        raw_response = await self.call_llm(ctx, prompt)
        logger.info("[image_creator_agent] raw LLM response:\n%s\n", raw_response[:300])

        parsed = _parse_image_prompt(raw_response)
        if parsed is None:
            return AgentResult(status="failed", error="LLM returned unparseable image prompt JSON")

        try:
            output = ImageCreatorOutput(
                content_item_id=content_item_id,
                prompt=parsed.get("prompt", ""),
                negative_prompt=parsed.get("negative_prompt", ""),
                style=parsed.get("style", "photorealistic"),
                aspect_ratio=parsed.get("aspect_ratio", "16:9"),
                alt_text=parsed.get("alt_text", ""),
                image_url="",
            )
        except ValidationError as exc:
            return AgentResult(status="failed", error=f"image prompt failed contract validation: {exc}")

        if not output.prompt:
            return AgentResult(status="failed", error="LLM returned empty image prompt")

        # ── Step 2: Call DALL-E 3 if API key is available ────────────────────
        image_url = ""
        image_generated = False
        try:
            image_url = await _generate_image_dalle(
                prompt=output.prompt,
                aspect_ratio=output.aspect_ratio,
            )
            image_generated = bool(image_url)
            if image_generated:
                logger.info("image_creator_agent: DALL-E 3 image generated: %s", image_url[:60])
        except Exception as exc:
            logger.info("image_creator_agent: DALL-E 3 skipped (%s) — prompt saved only", exc)

        # ── Step 3: Write to DB ───────────────────────────────────────────────
        image_body = json.dumps({
            "prompt": output.prompt,
            "negative_prompt": output.negative_prompt,
            "style": output.style,
            "aspect_ratio": output.aspect_ratio,
            "alt_text": output.alt_text,
            "image_url": image_url,
        }, ensure_ascii=False)

        await _write_item(content_item_id, image_body, ctx.db)
        await ctx.db.flush()

        return AgentResult(
            status="success",
            data={
                "content_item_id": content_item_id,
                "keyword": keyword,
                "prompt_preview": output.prompt[:120] + "...",
                "style": output.style,
                "aspect_ratio": output.aspect_ratio,
                "image_generated": image_generated,
                "image_url": image_url,
            },
            tokens_used=ctx.llm.last_tokens_used,
            cost_usd=ctx.llm.last_cost_usd,
        )


# ── DALL-E 3 call ──────────────────────────────────────────────────────────────

async def _generate_image_dalle(prompt: str, aspect_ratio: str) -> str:
    """Call DALL-E 3 and return the image URL. Raises if key missing or call fails."""
    from openai import AsyncOpenAI

    size_map = {"16:9": "1792x1024", "1:1": "1024x1024", "9:16": "1024x1792"}
    size = size_map.get(aspect_ratio, "1792x1024")

    client = AsyncOpenAI()
    response = await client.images.generate(
        model="dall-e-3",
        prompt=prompt,
        size=size,  # type: ignore[arg-type]
        quality="standard",
        n=1,
    )
    return response.data[0].url or ""


# ── DB helpers ─────────────────────────────────────────────────────────────────

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


async def _write_item(content_item_id: str, body: str, db: AsyncSession) -> None:
    await db.execute(
        text("UPDATE content_items SET body=:body, status='draft', updated_at=now() WHERE id=:id"),
        {"id": content_item_id, "body": body},
    )


# ── Parsing ────────────────────────────────────────────────────────────────────

def _parse_image_prompt(response: str) -> dict[str, Any] | None:
    if not response or not response.strip():
        return None
    cleaned = re.sub(r"```(?:json)?", "", response, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    if cleaned.startswith("{"):
        try:
            data = json.loads(cleaned)
            if isinstance(data, dict) and "prompt" in data:
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
