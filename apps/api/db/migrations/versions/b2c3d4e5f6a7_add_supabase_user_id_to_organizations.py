"""add supabase_user_id to organizations

Revision ID: b2c3d4e5f6a7
Revises: 6df9fe32fdcd
Create Date: 2026-04-29 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "6df9fe32fdcd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("supabase_user_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_organizations_supabase_user_id",
        "organizations",
        ["supabase_user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_organizations_supabase_user_id", table_name="organizations")
    op.drop_column("organizations", "supabase_user_id")
