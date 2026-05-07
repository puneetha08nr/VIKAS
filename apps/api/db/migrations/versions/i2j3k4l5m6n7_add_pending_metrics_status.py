"""add pending_metrics to keyword_status enum

Revision ID: i2j3k4l5m6n7
Revises: h1i2j3k4l5m6
Create Date: 2026-05-07 00:00:00.000000

Adds the pending_metrics status for keywords where data_source='pending'
and no volume/KD is available for confident rule-based validation.
These keywords await true-up when a real metrics API is restored.
PostgreSQL does not support removing enum values, so downgrade is a no-op.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "i2j3k4l5m6n7"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE keyword_status ADD VALUE IF NOT EXISTS 'pending_metrics'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values without full type recreation.
    pass
