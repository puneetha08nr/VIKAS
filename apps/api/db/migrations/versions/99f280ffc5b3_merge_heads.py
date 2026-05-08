"""merge heads

Revision ID: 99f280ffc5b3
Revises: h1i2j3k4l5m6, i2j3k4l5m6n7
Create Date: 2026-05-08 19:51:20.238306

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99f280ffc5b3'
down_revision: Union[str, None] = ('h1i2j3k4l5m6', 'i2j3k4l5m6n7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
