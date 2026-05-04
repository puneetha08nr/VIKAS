"""add unique constraint on (org_id, domain) in competitors table

Revision ID: f7a8b9c0d1e2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-04 00:00:00.000000

Enables ON CONFLICT upserts in competitor_monitor so re-running the agent
updates last_crawled_at rather than inserting duplicate rows.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_competitors_org_domain'
          AND conrelid = 'competitors'::regclass
    ) THEN
        ALTER TABLE competitors
            ADD CONSTRAINT uq_competitors_org_domain UNIQUE (org_id, domain);
    END IF;
END $$;
""")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE competitors DROP CONSTRAINT IF EXISTS uq_competitors_org_domain"
    )
