"""make opportunities.trend_score nullable for true-up mechanism

Revision ID: j3k4l5m6n7o8
Revises: i2j3k4l5m6n7
Create Date: 2026-05-07 00:00:00.000000

trend_score IS NULL is now the signal that an opportunity was created before
any real trend data was available. opportunity_scorer Mode 2 finds these rows
and back-fills them once trend_collector has written a non-neutral signal.

Existing rows with trend_score = 0 (DEFAULT) or = 5 (placeholder) are left
as-is; Mode 2 catches them via the (IS NULL OR = 5) condition.
"""
from alembic import op
import sqlalchemy as sa

revision = "j3k4l5m6n7o8"
down_revision = "i2j3k4l5m6n7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Allow NULL — existing NOT NULL DEFAULT 0 rows are unaffected
    op.alter_column(
        "opportunities",
        "trend_score",
        existing_type=sa.Double(),
        nullable=True,
        existing_nullable=False,
    )
    # Remove the DEFAULT so new rows without explicit trend_score get NULL, not 0
    op.execute("ALTER TABLE opportunities ALTER COLUMN trend_score DROP DEFAULT")


def downgrade() -> None:
    # Restore NOT NULL — set any NULLs back to 5.0 first
    op.execute("UPDATE opportunities SET trend_score = 5.0 WHERE trend_score IS NULL")
    op.alter_column(
        "opportunities",
        "trend_score",
        existing_type=sa.Double(),
        nullable=False,
        existing_nullable=True,
    )
    op.execute("ALTER TABLE opportunities ALTER COLUMN trend_score SET DEFAULT 0")
