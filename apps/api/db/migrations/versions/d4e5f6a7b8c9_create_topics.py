"""create topics table for topic_discovery agent

Revision ID: d4e5f6a7b8c9
Revises: c4d5e6f7a8b9
Create Date: 2026-05-05

Stores discovered content topics from free public sources:
  pytrends_rising, pytrends_top, google_suggest, reddit.

RLS policy: org_id = current_setting('app.current_org_id')::uuid
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("score", sa.Float, nullable=False, server_default="0.0"),
        sa.Column(
            "related_keywords",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_topics_org_id", "topics", ["org_id"])
    op.create_index("ix_topics_detected_at", "topics", ["detected_at"])

    op.execute("ALTER TABLE topics ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY topics_org_isolation ON topics
            USING (org_id = current_setting('app.current_org_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS topics_org_isolation ON topics;")
    op.drop_index("ix_topics_detected_at", table_name="topics")
    op.drop_index("ix_topics_org_id", table_name="topics")
    op.drop_table("topics")
