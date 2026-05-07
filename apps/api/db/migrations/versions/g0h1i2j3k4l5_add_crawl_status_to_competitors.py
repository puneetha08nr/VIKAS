"""add crawl_status column to competitors table

Revision ID: g0h1i2j3k4l5
Revises: f7a8b9c0d1e2
Create Date: 2026-05-06 00:00:00.000000

Tracks the crawl lifecycle per competitor row. UI derives display status
from last_crawled_at for now; this column is reserved for future real-time
queue status (queued | crawling) from the worker layer.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "g0h1i2j3k4l5"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE competitors ADD COLUMN IF NOT EXISTS "
        "crawl_status VARCHAR(20) NOT NULL DEFAULT 'never'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE competitors DROP COLUMN IF EXISTS crawl_status")
