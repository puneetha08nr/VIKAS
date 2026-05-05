"""create content_feedback and preference_summaries tables

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-05-05

content_feedback — human approval/edit/rejection events on generated content.
  Rows are processed = false until preference_learner aggregates them.

preference_summaries — rolled-up key/value preference signals per org.
  Written by preference_learner; injected into future agent prompts.
  Note: the existing `preferences` table stores individual learned patterns
  (pattern, weight, source). This table stores aggregated summary stats
  (approval_rate, edit_themes, rejected_patterns) per content_type.

RLS policies on both tables.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── content_feedback ──────────────────────────────────────────────────────
    op.create_table(
        "content_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),  # approved|edited|rejected
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("processed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_content_feedback_org_id", "content_feedback", ["org_id"])
    op.create_index("ix_content_feedback_processed", "content_feedback", ["processed"])

    op.execute(
        """
        ALTER TABLE content_feedback ENABLE ROW LEVEL SECURITY;
        CREATE POLICY content_feedback_org_isolation ON content_feedback
            USING (org_id = current_setting('app.current_org_id')::uuid);
        """
    )

    # ── preference_summaries ──────────────────────────────────────────────────
    op.create_table(
        "preference_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("preference_key", sa.String(100), nullable=False),
        sa.Column(
            "preference_value",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="'{}'::jsonb",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "org_id", "preference_key", name="uq_preference_summaries_org_key"
        ),
    )
    op.create_index("ix_preference_summaries_org_id", "preference_summaries", ["org_id"])

    op.execute(
        """
        ALTER TABLE preference_summaries ENABLE ROW LEVEL SECURITY;
        CREATE POLICY preference_summaries_org_isolation ON preference_summaries
            USING (org_id = current_setting('app.current_org_id')::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS preference_summaries_org_isolation ON preference_summaries;")
    op.drop_index("ix_preference_summaries_org_id", table_name="preference_summaries")
    op.drop_table("preference_summaries")

    op.execute("DROP POLICY IF EXISTS content_feedback_org_isolation ON content_feedback;")
    op.drop_index("ix_content_feedback_processed", table_name="content_feedback")
    op.drop_index("ix_content_feedback_org_id", table_name="content_feedback")
    op.drop_table("content_feedback")
