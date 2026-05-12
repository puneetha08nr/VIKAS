"""competitor_content: add (competitor_id, url) unique constraint, make title nullable

Revision ID: k4l5m6n7o8p9
Revises: j3k4l5m6n7o8
Create Date: 2026-05-08 00:00:00.000000

BUG-A-009: competitor_monitor fetches sitemap URLs but never writes them to
competitor_content. This migration enables idempotent inserts:

  ON CONFLICT (competitor_id, url) DO NOTHING

Title is made nullable because sitemap-stage rows have no title yet —
content_extractor fills it in on the next pass.
"""
from alembic import op

revision = "k4l5m6n7o8p9"
down_revision = "j3k4l5m6n7o8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make title nullable — sitemap inserts have no title yet
    op.execute(
        "ALTER TABLE competitor_content ALTER COLUMN title DROP NOT NULL"
    )

    # Add unique constraint to enable ON CONFLICT (competitor_id, url) DO NOTHING
    op.execute("""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_competitor_content_competitor_url'
          AND conrelid = 'competitor_content'::regclass
    ) THEN
        ALTER TABLE competitor_content
            ADD CONSTRAINT uq_competitor_content_competitor_url
            UNIQUE (competitor_id, url);
    END IF;
END $$;
""")


def downgrade() -> None:
    op.execute(
        "ALTER TABLE competitor_content "
        "DROP CONSTRAINT IF EXISTS uq_competitor_content_competitor_url"
    )
    op.execute(
        "ALTER TABLE competitor_content ALTER COLUMN title SET NOT NULL"
    )
