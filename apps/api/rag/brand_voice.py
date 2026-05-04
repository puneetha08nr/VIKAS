from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class BrandVoiceNotFoundError(Exception):
    def __init__(self, org_id: str) -> None:
        super().__init__(f"No brand voice configured for org '{org_id}'")
        self.org_id = org_id


class BrandVoiceLoader:

    async def load(self, org_id: str, db: AsyncSession) -> dict[str, Any]:
        """Return the brand_voice row for this org as a plain dict."""
        result = await db.execute(
            text(
                "SELECT tone, vocabulary, banned_phrases, style_rules "
                "FROM brand_voice WHERE org_id = :org_id"
            ),
            {"org_id": org_id},
        )
        row = result.fetchone()
        if row is None:
            raise BrandVoiceNotFoundError(org_id)

        return {
            "tone": row[0] or "",
            "vocabulary": row[1] if isinstance(row[1], list) else [],
            "banned_phrases": row[2] if isinstance(row[2], list) else [],
            "style_rules": row[3] if isinstance(row[3], dict) else {},
        }

    async def format_for_prompt(self, org_id: str, db: AsyncSession) -> str:
        """Return a compact prompt section describing brand voice constraints."""
        bv = await self.load(org_id, db)

        banned = ", ".join(bv["banned_phrases"]) if bv["banned_phrases"] else "none"
        style_parts = [f"{k}: {v}" for k, v in bv["style_rules"].items()]
        style = "; ".join(style_parts) if style_parts else "none"

        return f"Tone: {bv['tone']}. Avoid: {banned}. Style: {style}"
