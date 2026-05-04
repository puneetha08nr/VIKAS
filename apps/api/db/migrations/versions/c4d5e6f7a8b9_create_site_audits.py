"""create site_audits table

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-04

Each row is a point-in-time audit snapshot: keyword position distribution,
quick-win counts, and average GSC position for the org's site.
"""
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS site_audits (
            id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            site_url         VARCHAR(2048) NOT NULL,
            audit_date       DATE NOT NULL DEFAULT CURRENT_DATE,
            total_keywords   INTEGER NOT NULL DEFAULT 0,
            ranking_count    INTEGER NOT NULL DEFAULT 0,
            quick_wins_count INTEGER NOT NULL DEFAULT 0,
            not_ranking_count INTEGER NOT NULL DEFAULT 0,
            avg_position     DOUBLE PRECISION,
            gsc_rows_fetched INTEGER NOT NULL DEFAULT 0,
            summary          JSONB NOT NULL DEFAULT '{}',
            created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_site_audits_org_id "
        "ON site_audits (org_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_site_audits_audit_date "
        "ON site_audits (org_id, audit_date DESC)"
    )
    op.execute("ALTER TABLE site_audits ENABLE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY org_isolation ON site_audits
        USING (org_id::text = current_setting('app.current_org_id', true))
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS site_audits")
