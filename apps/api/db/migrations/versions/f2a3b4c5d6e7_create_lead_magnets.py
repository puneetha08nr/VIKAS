"""create lead_magnets table

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-05-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lead_magnets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("keyword", sa.Text, nullable=True),
        sa.Column("format", sa.String(50), nullable=False, server_default=sa.text("'checklist'")),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_lead_magnets_org_id", "lead_magnets", ["org_id"])
    op.execute("ALTER TABLE lead_magnets ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY lead_magnets_org_isolation ON lead_magnets
            USING (org_id = current_setting('app.current_org_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS lead_magnets_org_isolation ON lead_magnets;")
    op.drop_index("ix_lead_magnets_org_id", table_name="lead_magnets")
    op.drop_table("lead_magnets")
