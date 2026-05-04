"""create rank_tracking table

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-05-04

Each row is a historical snapshot of a keyword's GSC position.
status "quick_win" = position 11-30 (page 2-3, clostest to page 1).
"""
from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS rank_tracking (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            keyword_id       UUID NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
            keyword          VARCHAR(500) NOT NULL,
            position         DOUBLE PRECISION,
            previous_position DOUBLE PRECISION,
            status           VARCHAR(50) NOT NULL DEFAULT 'not_ranking',
            source           VARCHAR(100) NOT NULL DEFAULT 'gsc',
            checked_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rank_tracking_org_id "
        "ON rank_tracking (org_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rank_tracking_keyword_id "
        "ON rank_tracking (keyword_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rank_tracking_checked_at "
        "ON rank_tracking (checked_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_rank_tracking_status "
        "ON rank_tracking (org_id, status)"
    )
    op.execute("""
        ALTER TABLE rank_tracking ENABLE ROW LEVEL SECURITY
    """)
    op.execute("""
        CREATE POLICY org_isolation ON rank_tracking
        USING (org_id::text = current_setting('app.current_org_id', true))
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rank_tracking")
