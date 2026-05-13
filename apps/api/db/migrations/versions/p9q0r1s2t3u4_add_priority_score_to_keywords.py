"""add priority_score to keywords

Revision ID: p9q0r1s2t3u4
Revises: o8p9q0r1s2t3
Create Date: 2026-05-13 00:00:00.000000

keyword_research agent computes a priority_score (float) from volume,
kd, and intent and writes it on every INSERT/UPDATE. The column was
missing from the table, causing UndefinedColumnError at runtime.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "p9q0r1s2t3u4"
down_revision: str | Sequence[str] | None = "o8p9q0r1s2t3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "keywords",
        sa.Column("priority_score", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("keywords", "priority_score")
