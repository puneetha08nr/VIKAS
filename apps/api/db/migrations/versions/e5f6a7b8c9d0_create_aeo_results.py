"""create aeo_results table for aeo_scanner agent

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-05

Each row is a SERP snapshot for one keyword: whether an AI Overview,
featured snippet, or PAA block appeared, and the org's organic rank.
Used by aeo_scanner agent to track Answer Engine Optimization signals over time.

RLS policy: org_id = current_setting('app.current_org_id')::uuid
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aeo_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "keyword_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("keywords.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("keyword", sa.String(500), nullable=False),
        sa.Column("ai_overview", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("featured_snippet", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("paa_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("organic_position", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="'found'"),
        sa.Column(
            "scanned_at",
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
    op.create_index("ix_aeo_results_org_id", "aeo_results", ["org_id"])
    op.create_index("ix_aeo_results_keyword_id", "aeo_results", ["keyword_id"])
    op.create_index("ix_aeo_results_scanned_at", "aeo_results", ["scanned_at"])

    op.execute(
        """
        ALTER TABLE aeo_results ENABLE ROW LEVEL SECURITY;
        CREATE POLICY aeo_results_org_isolation ON aeo_results
            USING (org_id = current_setting('app.current_org_id')::uuid);
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS aeo_results_org_isolation ON aeo_results;")
    op.drop_index("ix_aeo_results_scanned_at", table_name="aeo_results")
    op.drop_index("ix_aeo_results_keyword_id", table_name="aeo_results")
    op.drop_index("ix_aeo_results_org_id", table_name="aeo_results")
    op.drop_table("aeo_results")
