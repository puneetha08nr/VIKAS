"""create video_jobs table for video handoff pipeline

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-05-05

Stores video production jobs created by video_handoff agent.
upload_token is the secret shared with the external video team — no auth
is required to POST a completed video, the token IS the credential.

RLS policy: org_id = current_setting('app.current_org_id')::uuid
upload_token index is unique and not org-scoped (lookup without org_id).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "video_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("script_text", sa.Text, nullable=True),
        sa.Column(
            "scenes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "broll_suggestions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "brand_voice",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending_video'"),
        ),
        sa.Column("video_url", sa.Text, nullable=True),
        sa.Column("thumbnail_url", sa.Text, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "upload_token",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
    op.create_index("ix_video_jobs_org_id", "video_jobs", ["org_id"])
    op.create_index(
        "ix_video_jobs_upload_token", "video_jobs", ["upload_token"], unique=True
    )
    op.create_index("ix_video_jobs_status", "video_jobs", ["status"])

    op.execute("ALTER TABLE video_jobs ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY video_jobs_org_isolation ON video_jobs
            USING (org_id = current_setting('app.current_org_id')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS video_jobs_org_isolation ON video_jobs;")
    op.drop_index("ix_video_jobs_status", table_name="video_jobs")
    op.drop_index("ix_video_jobs_upload_token", table_name="video_jobs")
    op.drop_index("ix_video_jobs_org_id", table_name="video_jobs")
    op.drop_table("video_jobs")
