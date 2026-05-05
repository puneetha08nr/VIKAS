"""broll_selector — finds stock video clips for each scene description.

No LLM. Pure Pexels API lookup.
  1. For each scene description, searches Pexels for matching stock video.
  2. Stores top 3 results per scene in broll_suggestions table.
  3. Returns total suggestions found.

Input params:
  scene_descriptions (list[str], required) — one string per scene

If PEXELS_API_KEY is missing → stores placeholder rows silently.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import text

from config.settings import settings
from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import BrollSelectorOutput
from integrations.pexels import PexelsIntegration

logger = logging.getLogger(__name__)


@register
class BrollSelectorAgent(BaseAgent):
    name = "broll_selector"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scenes: list[str] = ctx.params.get("scene_descriptions", [])
        if not scenes:
            return AgentResult(status="failed", error="scene_descriptions param is required")

        pexels = PexelsIntegration(api_key=getattr(settings, "pexels_api_key", ""))
        total_found = 0
        results: list[dict] = []

        for scene_text in scenes:
            scene_text = str(scene_text).strip()
            if not scene_text:
                continue

            videos = await pexels.search_videos(scene_text, per_page=3)

            if not videos:
                # Placeholder row so the scene is still represented
                videos = [{
                    "pexels_id": None,
                    "video_url": "",
                    "preview_url": "",
                    "width": 0,
                    "height": 0,
                }]

            for v in videos:
                await ctx.db.execute(
                    text(
                        "INSERT INTO broll_suggestions "
                        "  (id, org_id, scene_text, pexels_id, video_url, "
                        "   preview_url, width, height, created_at) "
                        "VALUES "
                        "  (CAST(:id AS uuid), :org_id, :scene_text, :pexels_id, "
                        "   :video_url, :preview_url, :width, :height, now())"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "org_id": ctx.org_id,
                        "scene_text": scene_text,
                        "pexels_id": v.get("pexels_id"),
                        "video_url": v.get("video_url", ""),
                        "preview_url": v.get("preview_url", ""),
                        "width": v.get("width", 0),
                        "height": v.get("height", 0),
                    },
                )
                if v.get("pexels_id"):
                    total_found += 1

            results.append(BrollSelectorOutput(
                scene_text=scene_text,
                suggestions_found=len([v for v in videos if v.get("pexels_id")]),
                status="ok" if any(v.get("pexels_id") for v in videos) else "no_results",
            ).model_dump())

        await ctx.db.flush()

        return AgentResult(
            status="success",
            data={
                "scenes_processed": len(results),
                "total_suggestions_found": total_found,
                "scenes": results,
            },
        )
