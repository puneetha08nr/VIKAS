"""create strategy_reports table

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-05-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opportunities_analyzed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("recommendations", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'success'")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_strategy_reports_org_id", "strategy_reports", ["org_id"])
    op.execute("ALTER TABLE strategy_reports ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY strategy_reports_org_isolation ON strategy_reports
            USING (org_id = current_setting('app.current_org_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS strategy_reports_org_isolation ON strategy_reports;")
    op.drop_index("ix_strategy_reports_org_id", table_name="strategy_reports")
    op.drop_table("strategy_reports")
