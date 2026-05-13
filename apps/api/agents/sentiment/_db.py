"""Shared DB helpers for sentiment Stage 1 collector agents."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, cast

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_INSERT_SQL = text("""
    INSERT INTO raw_mentions (
        id, org_id, source, source_identifier, external_id,
        url, title, body, author, published_at,
        language_raw, engagement_raw, status,
        scheme_hint, district_hint, created_at
    ) VALUES (
        gen_random_uuid(), :org_id, :source, :source_identifier, :external_id,
        :url, :title, :body, :author, :published_at,
        '', CAST(:engagement_raw AS jsonb), 'pending',
        CAST(:scheme_hint AS jsonb), CAST(:district_hint AS jsonb), now()
    )
    ON CONFLICT (org_id, source, external_id) DO NOTHING
""")


async def save_mentions(
    mentions: list[dict[str, Any]],
    source: str,
    scheme_key: str,
    district_key: str,
    org_id: str,
    db: AsyncSession,
) -> tuple[int, int]:
    """Insert mention dicts into raw_mentions.

    Returns (inserted_count, skipped_count).
    Skips on duplicate (org_id, source, external_id) via ON CONFLICT DO NOTHING.
    """
    inserted = 0
    skipped = 0
    scheme_hint = json.dumps([scheme_key] if scheme_key else [])
    district_hint = json.dumps([district_key] if district_key else [])

    for m in mentions:
        params = {
            "org_id": org_id,
            "source": source,
            "source_identifier": m.get("source_identifier", ""),
            "external_id": m.get("external_id", ""),
            "url": m.get("url", ""),
            "title": (m.get("title") or "")[:2000],
            "body": (m.get("body") or "")[:10000],
            "author": (m.get("author") or "")[:500],
            "published_at": _parse_dt(m.get("published_at")),
            "engagement_raw": json.dumps(m.get("engagement_raw") or {}),
            "scheme_hint": scheme_hint,
            "district_hint": district_hint,
        }
        if not params["external_id"]:
            logger.debug("save_mentions: skipping mention with no external_id")
            skipped += 1
            continue
        raw_result: Any = await db.execute(_INSERT_SQL, params)
        result = cast(Any, raw_result)
        if result.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    await db.flush()
    return inserted, skipped


def _parse_dt(value: Any) -> datetime | None:
    """Parse ISO 8601 / RFC 2822 datetime string to a timezone-aware datetime.

    Returns None on any failure — the field is nullable in raw_mentions.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(str(value))
    except Exception:
        return None
