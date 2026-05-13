"""merge migration heads

Revision ID: l5m6n7o8p9q0
Revises: k4l5m6n7o8p9, h1i2j3k4l5m6
Create Date: 2026-05-08 00:00:00.000000

Merges the keywords unique-constraint branch (h1i2j3k4l5m6) with the
competitor_content URL constraint branch (k4l5m6n7o8p9) into a single head.
"""
revision = "l5m6n7o8p9q0"
down_revision = ("k4l5m6n7o8p9", "h1i2j3k4l5m6")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
