"""add unique constraint on (org_id, keyword) in keywords table

Revision ID: h1i2j3k4l5m6
Revises: g0h1i2j3k4l5
Create Date: 2026-05-06 00:00:00.000000

Prevents duplicate keyword rows per org. Existing duplicates must be cleaned
before this migration runs (keep earliest created_at per org+keyword pair).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "h1i2j3k4l5m6"
down_revision: str | None = "g0h1i2j3k4l5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_keywords_org_keyword'
          AND conrelid = 'keywords'::regclass
    ) THEN
        -- Remove duplicates before adding constraint
        DELETE FROM keywords
        WHERE id NOT IN (
            SELECT DISTINCT ON (org_id, keyword) id
            FROM keywords
            ORDER BY org_id, keyword, created_at ASC
        );
        ALTER TABLE keywords
            ADD CONSTRAINT uq_keywords_org_keyword UNIQUE (org_id, keyword);
    END IF;
END $$;
""")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE keywords DROP CONSTRAINT IF EXISTS uq_keywords_org_keyword"
    )
