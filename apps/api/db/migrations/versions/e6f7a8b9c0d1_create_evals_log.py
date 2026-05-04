"""create evals_log table for eval framework results

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-05-01 00:00:00.000000

evals_log stores results from all three eval types:
  structural  — automated CI checks (output shape, types, DB write)
  relevance   — weekly LLM-as-judge quality scores
  ground_truth — monthly human spot-check ratings (1-5)

org_id is nullable: eval runner runs are not tenant-scoped.
No RLS policy — this is operational data, not tenant data.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, None] = "22619f407a67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "evals_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("eval_type", sa.String(20), nullable=False),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("threshold", sa.Float, nullable=True),
        sa.Column("passed", sa.Boolean, nullable=True),
        sa.Column("inputs", postgresql.JSONB, nullable=True),
        sa.Column("outputs", postgresql.JSONB, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_evals_log_agent_name", "evals_log", ["agent_name"])
    op.create_index("ix_evals_log_run_at", "evals_log", ["run_at"])
    op.create_index("ix_evals_log_agent_type", "evals_log", ["agent_name", "eval_type"])


def downgrade() -> None:
    op.drop_index("ix_evals_log_agent_type", table_name="evals_log")
    op.drop_index("ix_evals_log_run_at", table_name="evals_log")
    op.drop_index("ix_evals_log_agent_name", table_name="evals_log")
    op.drop_table("evals_log")
