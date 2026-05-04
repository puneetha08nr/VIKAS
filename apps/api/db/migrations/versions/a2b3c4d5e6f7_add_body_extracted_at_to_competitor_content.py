"""add body and extracted_at to competitor_content

Revision ID: a2b3c4d5e6f7
Revises: f7a8b9c0d1e2
Create Date: 2026-05-04

Uses IF NOT EXISTS guards (see ISSUES_AND_FIXES.md Issue 5).
"""
from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE competitor_content ADD COLUMN IF NOT EXISTS body TEXT")
    op.execute(
        "ALTER TABLE competitor_content "
        "ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMP WITH TIME ZONE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE competitor_content DROP COLUMN IF EXISTS extracted_at")
    op.execute("ALTER TABLE competitor_content DROP COLUMN IF EXISTS body")
