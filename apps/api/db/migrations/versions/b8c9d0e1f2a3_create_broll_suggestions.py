"""create broll_suggestions table

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-05-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "broll_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scene_text", sa.Text, nullable=True),
        sa.Column("pexels_id", sa.Integer, nullable=True),
        sa.Column("video_url", sa.Text, nullable=True),
        sa.Column("preview_url", sa.Text, nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_broll_suggestions_org_id", "broll_suggestions", ["org_id"])
    op.execute("ALTER TABLE broll_suggestions ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY broll_suggestions_org_isolation ON broll_suggestions
            USING (org_id = current_setting('app.current_org_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS broll_suggestions_org_isolation ON broll_suggestions;")
    op.drop_index("ix_broll_suggestions_org_id", table_name="broll_suggestions")
    op.drop_table("broll_suggestions")
