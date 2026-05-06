"""video_scriptwriter — generates a video script from an article.

Standard tier LLM. Writes to video_scripts table.

Input params:
  article_id (str, required)
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import VideoScriptwriterOutput
from core.prompt_registry import PromptRegistry

logger = logging.getLogger(__name__)


@register
class VideoScriptwriterAgent(BaseAgent):
    name = "video_scriptwriter"
    tier = "standard"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        article_id = str(ctx.params.get("article_id", "")).strip()
        if not article_id:
            return AgentResult(status="failed", error="article_id param is required")

        article = await _load_article(article_id, ctx.org_id, ctx.db)
        if not article:
            return AgentResult(status="failed", error=f"Article '{article_id}' not found")

        template = await PromptRegistry().get(self.name, ctx.db)
        prompt = (
            template
            .replace("ARTICLE_TITLE", article.get("title", ""))
            .replace("ARTICLE_BODY", (article.get("body_html", "") or "")[:2000])
            .replace("KEYWORD", article.get("keyword", ""))
        )

        raw = await self.call_llm(ctx, prompt)
        scenes = _parse_scenes(raw)

        total_duration = sum(s.get("duration", 10) for s in scenes if isinstance(s, dict))
        script_id = str(uuid.uuid4())

        await ctx.db.execute(
            text(
                "INSERT INTO video_scripts "
                "  (id, org_id, article_id, scenes, total_duration_seconds, status, created_at) "
                "VALUES "
                "  (CAST(:id AS uuid), :org_id, CAST(:article_id AS uuid), "
                "   CAST(:scenes AS jsonb), :total_duration_seconds, 'draft', now())"
            ),
            {
                "id": script_id,
                "org_id": ctx.org_id,
                "article_id": article_id,
                "scenes": json.dumps(scenes),
                "total_duration_seconds": total_duration,
            },
        )
        await ctx.db.flush()

        output = VideoScriptwriterOutput(
            video_script_id=script_id,
            article_id=article_id,
            total_duration_seconds=total_duration,
            scene_count=len(scenes),
            status="draft",
        )
        return AgentResult(status="success", data=output.model_dump())


async def _load_article(article_id: str, org_id: str, db) -> dict | None:
    result = await db.execute(
        text("SELECT id, keyword, title, body_html FROM articles "
             "WHERE id = CAST(:id AS uuid) AND org_id = :org_id"),
        {"id": article_id, "org_id": org_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "id": str(row[0]),
        "keyword": row[1] or "",
        "title": row[2] or "",
        "body_html": row[3] or "",
    }


def _parse_scenes(raw: str) -> list[dict]:
    try:
        clean = raw.strip().lstrip("```json").lstrip("```").rstrip("```")
        parsed = json.loads(clean)
        if isinstance(parsed, list):
            scenes = []
            for item in parsed:
                if isinstance(item, dict):
                    scenes.append({
                        "voiceover": item.get("voiceover", item.get("text", "")),
                        "visual_direction": item.get("visual_direction", item.get("visual", "")),
                        "duration": int(item.get("duration", 10)),
                    })
                elif isinstance(item, str):
                    scenes.append({"voiceover": item, "visual_direction": "", "duration": 10})
            return scenes
        if isinstance(parsed, dict) and "scenes" in parsed:
            return _parse_scenes(json.dumps(parsed["scenes"]))
    except Exception:
        pass
    # Fallback: treat each non-empty line as a voiceover
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return [{"voiceover": ln, "visual_direction": "", "duration": 10} for ln in lines[:9]]
