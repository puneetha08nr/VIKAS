"""create articles table

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-05-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d0e1f2a3b4c5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("article_plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("keyword", sa.Text, nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("body_html", sa.Text, nullable=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("published_url", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_articles_org_id", "articles", ["org_id"])
    op.create_index("ix_articles_article_plan_id", "articles", ["article_plan_id"])
    op.create_index("ix_articles_status", "articles", ["status"])
    op.execute("ALTER TABLE articles ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY articles_org_isolation ON articles
            USING (org_id = current_setting('app.current_org_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS articles_org_isolation ON articles;")
    op.drop_index("ix_articles_status", table_name="articles")
    op.drop_index("ix_articles_article_plan_id", table_name="articles")
    op.drop_index("ix_articles_org_id", table_name="articles")
    op.drop_table("articles")
