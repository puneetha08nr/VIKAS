"""create article_plans table

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-05-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "article_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("keyword", sa.Text, nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("meta_description", sa.Text, nullable=True),
        sa.Column("outline", postgresql.JSONB(astext_type=sa.Text()),
                  nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("word_count_target", sa.Integer, nullable=True),
        sa.Column("content_angle", sa.Text, nullable=True),
        sa.Column("cta", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'planned'")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_article_plans_org_id", "article_plans", ["org_id"])
    op.create_index("ix_article_plans_opportunity_id", "article_plans", ["opportunity_id"])
    op.execute("ALTER TABLE article_plans ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY article_plans_org_isolation ON article_plans
            USING (org_id = current_setting('app.current_org_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS article_plans_org_isolation ON article_plans;")
    op.drop_index("ix_article_plans_opportunity_id", table_name="article_plans")
    op.drop_index("ix_article_plans_org_id", table_name="article_plans")
    op.drop_table("article_plans")
