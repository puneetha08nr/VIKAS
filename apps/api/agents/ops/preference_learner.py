"""preference_learner — aggregates human feedback into reusable preference signals.

Pure DB, no LLM, no external API.

Reads unprocessed rows from content_feedback (processed = false), groups them
per content_type, and computes:
  - approval_rate, edit_rate, rejection_rate
  - edit_themes: notes text from edited rows (raw, for prompt injection)
  - rejected_patterns: notes text from rejected rows

Each derived signal is upserted to preference_summaries as a key/value pair:
  {content_type}_approval_stats  → {approved, edited, rejected, total, approval_rate, ...}
  {content_type}_edit_themes     → {notes: [...], count: N}
  {content_type}_rejected_patterns → {notes: [...], count: N}

After writing, all processed rows are marked processed = true.

Input params: none required (operates on the calling org's feedback).
Output: list of PreferenceLearnerOutput, one per content_type that had feedback.
"""
import json
import logging
from collections import defaultdict

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import PreferenceLearnerOutput

logger = logging.getLogger(__name__)

_VALID_ACTIONS = frozenset({"approved", "edited", "rejected"})


@register
class PreferenceLearnerAgent(BaseAgent):
    name = "preference_learner"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        # ── Step 1: Fetch unprocessed feedback ───────────────────────────────
        rows = await _fetch_unprocessed(ctx.org_id, ctx.db)

        if not rows:
            return AgentResult(
                status="success",
                data={
                    "content_types_processed": 0,
                    "preferences_written": 0,
                    "feedback_rows_processed": 0,
                    "message": "No unprocessed feedback found",
                },
            )

        # ── Step 2: Group by content_type ────────────────────────────────────
        # bucket[content_type] = {action: [notes, ...], ...}
        buckets: dict[str, dict[str, list[str]]] = defaultdict(
            lambda: {"approved": [], "edited": [], "rejected": []}
        )
        row_ids: list[str] = []

        for row in rows:
            row_id = str(row[0])
            content_type = str(row[1]).strip() or "unknown"
            action = str(row[2]).strip().lower()
            notes = str(row[3]).strip() if row[3] else ""

            if action not in _VALID_ACTIONS:
                logger.warning(
                    "preference_learner: unknown action %r — skipping row %s",
                    action,
                    row_id,
                )
                continue

            buckets[content_type][action].append(notes)
            row_ids.append(row_id)

        # ── Step 3: Compute signals + upsert ─────────────────────────────────
        summaries: list[dict] = []
        total_prefs_written = 0

        for content_type, counts in buckets.items():
            approved_n = len(counts["approved"])
            edited_n = len(counts["edited"])
            rejected_n = len(counts["rejected"])
            total = approved_n + edited_n + rejected_n

            if total == 0:
                continue

            approval_rate = round(approved_n / total, 4)
            edit_rate = round(edited_n / total, 4)
            rejection_rate = round(rejected_n / total, 4)

            # Signals to upsert
            signals: dict[str, dict] = {
                f"{content_type}_approval_stats": {
                    "approved": approved_n,
                    "edited": edited_n,
                    "rejected": rejected_n,
                    "total": total,
                    "approval_rate": approval_rate,
                    "edit_rate": edit_rate,
                    "rejection_rate": rejection_rate,
                },
                f"{content_type}_edit_themes": {
                    "notes": [n for n in counts["edited"] if n],
                    "count": edited_n,
                },
                f"{content_type}_rejected_patterns": {
                    "notes": [n for n in counts["rejected"] if n],
                    "count": rejected_n,
                },
            }

            written = 0
            for key, value in signals.items():
                await _upsert_preference(ctx.org_id, key, value, ctx.db)
                written += 1

            total_prefs_written += written

            raw = {
                "org_id": ctx.org_id,
                "content_type": content_type,
                "total_feedback": total,
                "approved": approved_n,
                "edited": edited_n,
                "rejected": rejected_n,
                "approval_rate": approval_rate,
                "edit_rate": edit_rate,
                "rejection_rate": rejection_rate,
                "preferences_written": written,
            }
            try:
                summaries.append(PreferenceLearnerOutput(**raw).model_dump())
            except ValidationError as exc:
                logger.warning("preference_learner: validation error for %r: %s", content_type, exc)

        # ── Step 4: Mark rows as processed ───────────────────────────────────
        if row_ids:
            await _mark_processed(row_ids, ctx.db)

        await ctx.db.flush()

        return AgentResult(
            status="success",
            data={
                "content_types_processed": len(summaries),
                "preferences_written": total_prefs_written,
                "feedback_rows_processed": len(row_ids),
                "summaries": summaries,
            },
        )


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_unprocessed(org_id: str, db: AsyncSession) -> list:
    result = await db.execute(
        text(
            "SELECT id, content_type, action, notes "
            "FROM content_feedback "
            "WHERE org_id = :org_id AND processed = false "
            "ORDER BY created_at ASC"
        ),
        {"org_id": org_id},
    )
    return list(result.fetchall())


async def _upsert_preference(
    org_id: str,
    key: str,
    value: dict,
    db: AsyncSession,
) -> None:
    await db.execute(
        text(
            "INSERT INTO preference_summaries "
            "  (id, org_id, preference_key, preference_value, updated_at) "
            "VALUES "
            "  (gen_random_uuid(), :org_id, :key, CAST(:value AS jsonb), now()) "
            "ON CONFLICT (org_id, preference_key) DO UPDATE SET "
            "  preference_value = EXCLUDED.preference_value, "
            "  updated_at = now()"
        ),
        {"org_id": org_id, "key": key, "value": json.dumps(value)},
    )


async def _mark_processed(row_ids: list[str], db: AsyncSession) -> None:
    await db.execute(
        text(
            "UPDATE content_feedback SET processed = true "
            "WHERE id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"ids": row_ids},
    )
