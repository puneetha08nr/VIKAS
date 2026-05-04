"""add_intent_reason_to_keywords

Revision ID: 22619f407a67
Revises: d5e6f7a8b9c0
Create Date: 2026-04-30 14:18:59.271689

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '22619f407a67'
down_revision: str | None = 'd5e6f7a8b9c0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE keywords ADD COLUMN IF NOT EXISTS intent VARCHAR(50)")
    op.execute("ALTER TABLE keywords ADD COLUMN IF NOT EXISTS reason TEXT")
    op.execute("ALTER TABLE keywords ADD COLUMN IF NOT EXISTS source_run_id UUID")


def downgrade() -> None:
    op.drop_column('keywords', 'source_run_id')
    op.drop_column('keywords', 'reason')
    op.drop_column('keywords', 'intent')
