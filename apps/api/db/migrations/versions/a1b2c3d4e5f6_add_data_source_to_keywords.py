"""add data_source column to keywords

Revision ID: a1b2c3d4e5f6
Revises: e6f7a8b9c0d1
Create Date: 2026-05-01 00:00:00.000000

data_source tracks whether metrics came from DataForSEO ('dataforseo')
or were estimated by the LLM ('llm_estimate'). Default is 'llm_estimate'
so existing rows get the conservative fallback value.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE keywords ADD COLUMN IF NOT EXISTS "
        "data_source VARCHAR(30) NOT NULL DEFAULT 'llm_estimate'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE keywords DROP COLUMN IF EXISTS data_source")
