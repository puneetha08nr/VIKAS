"""preference_loader — reads learned preferences from preference_summaries
and formats them as prompt injection text for content agents.

Used by: article_writer, linkedin_agent, twitter_agent, newsletter_agent
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def load_preferences(org_id: str, content_type: str, db: AsyncSession) -> str:
    """Load learned preferences for a content type and format for prompt injection.

    content_type: 'article' | 'linkedin' | 'twitter' | 'newsletter'

    Returns a formatted string to inject as LEARNED_PREFERENCES in prompts.
    Returns empty string if no preferences found.
    """
    try:
        result = await db.execute(
            text(
                "SELECT preference_key, preference_value "
                "FROM preference_summaries "
                "WHERE org_id = :org_id "
                "  AND preference_key LIKE :prefix "
                "ORDER BY updated_at DESC"
            ),
            {"org_id": org_id, "prefix": f"{content_type}_%"},
        )
        rows = result.fetchall()
        if not rows:
            return ""

        lines: list[str] = ["Based on previous human feedback, apply these preferences:"]

        for key, value in rows:
            if not value:
                continue
            data = value if isinstance(value, dict) else json.loads(value)

            # Approval stats
            if key.endswith("_approval_stats"):
                approval_rate = data.get("approval_rate", 0)
                total = data.get("total", 0)
                if total > 0:
                    lines.append(
                        f"- Approval rate: {approval_rate:.0%} "
                        f"({data.get('approved',0)} approved, "
                        f"{data.get('edited',0)} edited, "
                        f"{data.get('rejected',0)} rejected out of {total})"
                    )

            # Edit themes — what humans changed
            elif key.endswith("_edit_themes"):
                notes = [n for n in data.get("notes", []) if n.strip()]
                if notes:
                    lines.append("- Common edits humans made:")
                    for note in notes[:5]:  # max 5 examples
                        lines.append(f"  • {note}")

            # Rejected patterns — what to avoid
            elif key.endswith("_rejected_patterns"):
                notes = [n for n in data.get("notes", []) if n.strip()]
                if notes:
                    lines.append("- Patterns that were rejected (avoid these):")
                    for note in notes[:5]:
                        lines.append(f"  • {note}")

        if len(lines) <= 1:
            return ""

        return "\n".join(lines)

    except Exception as exc:
        logger.warning("preference_loader: failed to load preferences: %s", exc)
        return ""
