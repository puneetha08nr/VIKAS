"""merge l5m6 and 99f280 heads

Revision ID: n7o8p9q0r1s2
Revises: l5m6n7o8p9q0, 99f280ffc5b3
Create Date: 2026-05-12 00:00:00.000000

Merges the pending-metrics branch (99f280ffc5b3) with the main chain
(l5m6n7o8p9q0) into a single head.
"""
from collections.abc import Sequence

revision: str = "n7o8p9q0r1s2"
down_revision: str | Sequence[str] | None = ("l5m6n7o8p9q0", "99f280ffc5b3")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
