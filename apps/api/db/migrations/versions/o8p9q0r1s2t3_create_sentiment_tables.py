"""create sentiment analysis tables

Revision ID: o8p9q0r1s2t3
Revises: n7o8p9q0r1s2
Create Date: 2026-05-12 00:00:00.000000

Creates 8 tables for the production sentiment analyser subsystem:
  raw_mentions, relevant_mentions, analyzed_mentions, sentiment_signals,
  scheme_patterns, district_patterns, theme_taxonomy, source_credibility

theme_taxonomy is global (no org_id, no RLS).
All other tables are per-org with RLS.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "o8p9q0r1s2t3"
down_revision: str | Sequence[str] | None = "n7o8p9q0r1s2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TS = sa.TIMESTAMP(timezone=True)
_TEXT = sa.Text
_STR = sa.String


def upgrade() -> None:
    # ── 1. theme_taxonomy (global reference, no RLS) ──────────────────────────
    op.create_table(
        "theme_taxonomy",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("theme_key", _STR(100), nullable=False),
        sa.Column("label_en", _STR(200), nullable=False, server_default=""),
        sa.Column("label_ta", _STR(200), nullable=False, server_default=""),
        sa.Column("description", _TEXT, nullable=False, server_default=""),
        sa.Column("patterns_en", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("patterns_ta", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_theme_taxonomy_key", "theme_taxonomy", ["theme_key"])
    op.create_index("ix_theme_taxonomy_is_active", "theme_taxonomy", ["is_active"])

    # ── 2. raw_mentions ───────────────────────────────────────────────────────
    op.create_table(
        "raw_mentions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", _STR(50), nullable=False),
        sa.Column("source_identifier", _STR(500), nullable=False, server_default=""),
        sa.Column("external_id", _STR(500), nullable=False),
        sa.Column("url", _TEXT, nullable=False, server_default=""),
        sa.Column("title", _TEXT, nullable=False, server_default=""),
        sa.Column("body", _TEXT, nullable=False, server_default=""),
        sa.Column("author", _TEXT, nullable=False, server_default=""),
        sa.Column("published_at", _TS, nullable=True),
        sa.Column("collected_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("language_raw", _STR(20), nullable=False, server_default=""),
        sa.Column("engagement_raw", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", _STR(20), nullable=False, server_default="pending"),
        sa.Column("scheme_hint", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("district_hint", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_raw_mentions_source_id", "raw_mentions", ["org_id", "source", "external_id"]
    )
    op.create_index("ix_raw_mentions_org_id", "raw_mentions", ["org_id"])
    op.create_index("ix_raw_mentions_published_at", "raw_mentions", ["published_at"])
    op.create_index("ix_raw_mentions_status", "raw_mentions", ["status"])
    op.create_index("ix_raw_mentions_collected_at", "raw_mentions", ["collected_at"])
    op.execute("""
        CREATE POLICY raw_mentions_org_isolation ON raw_mentions
        USING (org_id = current_setting('app.current_org_id')::uuid)
    """)
    op.execute("ALTER TABLE raw_mentions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE raw_mentions FORCE ROW LEVEL SECURITY")

    # ── 3. relevant_mentions ──────────────────────────────────────────────────
    op.create_table(
        "relevant_mentions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_mention_id", UUID(as_uuid=True),
                  sa.ForeignKey("raw_mentions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", _STR(50), nullable=False, server_default=""),
        sa.Column("source_identifier", _STR(500), nullable=False, server_default=""),
        sa.Column("url", _TEXT, nullable=False, server_default=""),
        sa.Column("title", _TEXT, nullable=False, server_default=""),
        sa.Column("body_clean", _TEXT, nullable=False, server_default=""),
        sa.Column("language", _STR(20), nullable=False, server_default="unknown"),
        sa.Column("language_confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("matched_scheme", _STR(200), nullable=False, server_default=""),
        sa.Column("matched_district", _STR(200), nullable=False, server_default=""),
        sa.Column("published_at", _TS, nullable=True),
        sa.Column("source_weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("vader_score", sa.Float, nullable=True),
        sa.Column("vader_confidence", sa.Float, nullable=True),
        sa.Column(
            "minhash_signature", JSONB, nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", _STR(30), nullable=False, server_default="pending_analysis"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_relevant_mentions_org_id", "relevant_mentions", ["org_id"])
    op.create_index(
        "ix_relevant_mentions_raw_mention_id", "relevant_mentions", ["raw_mention_id"]
    )
    op.create_index(
        "ix_relevant_mentions_matched_scheme", "relevant_mentions", ["matched_scheme"]
    )
    op.create_index(
        "ix_relevant_mentions_matched_district", "relevant_mentions", ["matched_district"]
    )
    op.create_index("ix_relevant_mentions_published_at", "relevant_mentions", ["published_at"])
    op.create_index("ix_relevant_mentions_status", "relevant_mentions", ["status"])
    op.execute("""
        CREATE POLICY relevant_mentions_org_isolation ON relevant_mentions
        USING (org_id = current_setting('app.current_org_id')::uuid)
    """)
    op.execute("ALTER TABLE relevant_mentions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE relevant_mentions FORCE ROW LEVEL SECURITY")

    # ── 4. analyzed_mentions ──────────────────────────────────────────────────
    op.create_table(
        "analyzed_mentions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relevant_mention_id", UUID(as_uuid=True),
                  sa.ForeignKey("relevant_mentions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("matched_scheme", _STR(200), nullable=False, server_default=""),
        sa.Column("matched_district", _STR(200), nullable=False, server_default=""),
        sa.Column("polarity", _STR(20), nullable=False, server_default="neutral"),
        sa.Column("polarity_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("polarity_confidence", sa.Float, nullable=False, server_default="0"),
        sa.Column("polarity_method", _STR(30), nullable=False, server_default="vader"),
        sa.Column("contains_sarcasm", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_about_scheme", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("themes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("theme_confidence", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("entities", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("prompt_hash", _STR(64), nullable=False, server_default=""),
        sa.Column("analyzed_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_analyzed_mentions_org_id", "analyzed_mentions", ["org_id"])
    op.create_index(
        "ix_analyzed_mentions_relevant_mention_id",
        "analyzed_mentions", ["relevant_mention_id"],
    )
    op.create_index("ix_analyzed_mentions_polarity", "analyzed_mentions", ["polarity"])
    op.create_index(
        "ix_analyzed_mentions_matched_scheme", "analyzed_mentions", ["matched_scheme"]
    )
    op.create_index(
        "ix_analyzed_mentions_matched_district", "analyzed_mentions", ["matched_district"]
    )
    op.create_index("ix_analyzed_mentions_analyzed_at", "analyzed_mentions", ["analyzed_at"])
    op.execute("""
        CREATE POLICY analyzed_mentions_org_isolation ON analyzed_mentions
        USING (org_id = current_setting('app.current_org_id')::uuid)
    """)
    op.execute("ALTER TABLE analyzed_mentions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE analyzed_mentions FORCE ROW LEVEL SECURITY")

    # ── 5. sentiment_signals ──────────────────────────────────────────────────
    op.create_table(
        "sentiment_signals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheme_key", _STR(200), nullable=False),
        sa.Column("district_key", _STR(200), nullable=False),
        sa.Column("signal_date", sa.Date, nullable=False),
        sa.Column("window_hours", sa.Integer, nullable=False, server_default="24"),
        sa.Column("mention_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("weighted_mention_count", sa.Float, nullable=False, server_default="0"),
        sa.Column("positive_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("negative_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("neutral_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("mixed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("avg_polarity_score", sa.Float, nullable=True),
        sa.Column("weighted_avg_polarity_score", sa.Float, nullable=True),
        sa.Column("dominant_polarity", _STR(20), nullable=False, server_default="neutral"),
        sa.Column("dominant_themes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("spike_detected", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("spike_analysis", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("computed_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_sentiment_signals_key",
        "sentiment_signals",
        ["org_id", "scheme_key", "district_key", "signal_date", "window_hours"],
    )
    op.create_index("ix_sentiment_signals_org_id", "sentiment_signals", ["org_id"])
    op.create_index("ix_sentiment_signals_scheme_key", "sentiment_signals", ["scheme_key"])
    op.create_index("ix_sentiment_signals_district_key", "sentiment_signals", ["district_key"])
    op.create_index("ix_sentiment_signals_signal_date", "sentiment_signals", ["signal_date"])
    op.create_index(
        "ix_sentiment_signals_spike_detected", "sentiment_signals", ["spike_detected"]
    )
    op.execute("""
        CREATE POLICY sentiment_signals_org_isolation ON sentiment_signals
        USING (org_id = current_setting('app.current_org_id')::uuid)
    """)
    op.execute("ALTER TABLE sentiment_signals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sentiment_signals FORCE ROW LEVEL SECURITY")

    # ── 6. scheme_patterns ────────────────────────────────────────────────────
    op.create_table(
        "scheme_patterns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheme_key", _STR(200), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("total_mentions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("net_polarity", sa.Float, nullable=False, server_default="0"),
        sa.Column("dominant_themes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("top_districts", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("velocity", sa.Float, nullable=False, server_default="0"),
        sa.Column("trend_direction", _STR(20), nullable=False, server_default="stable"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_scheme_patterns_org_id", "scheme_patterns", ["org_id"])
    op.create_index("ix_scheme_patterns_scheme_key", "scheme_patterns", ["scheme_key"])
    op.create_index("ix_scheme_patterns_period_start", "scheme_patterns", ["period_start"])
    op.execute("""
        CREATE POLICY scheme_patterns_org_isolation ON scheme_patterns
        USING (org_id = current_setting('app.current_org_id')::uuid)
    """)
    op.execute("ALTER TABLE scheme_patterns ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scheme_patterns FORCE ROW LEVEL SECURITY")

    # ── 7. district_patterns ──────────────────────────────────────────────────
    op.create_table(
        "district_patterns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("district_key", _STR(200), nullable=False),
        sa.Column("period_start", sa.Date, nullable=False),
        sa.Column("period_end", sa.Date, nullable=False),
        sa.Column("total_mentions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("net_polarity", sa.Float, nullable=False, server_default="0"),
        sa.Column("top_schemes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("top_themes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("velocity", sa.Float, nullable=False, server_default="0"),
        sa.Column("trend_direction", _STR(20), nullable=False, server_default="stable"),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_district_patterns_org_id", "district_patterns", ["org_id"])
    op.create_index("ix_district_patterns_district_key", "district_patterns", ["district_key"])
    op.create_index("ix_district_patterns_period_start", "district_patterns", ["period_start"])
    op.execute("""
        CREATE POLICY district_patterns_org_isolation ON district_patterns
        USING (org_id = current_setting('app.current_org_id')::uuid)
    """)
    op.execute("ALTER TABLE district_patterns ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE district_patterns FORCE ROW LEVEL SECURITY")

    # ── 8. source_credibility ─────────────────────────────────────────────────
    op.create_table(
        "source_credibility",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True),
                  sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_identifier", _STR(500), nullable=False),
        sa.Column("source_handle", _STR(500), nullable=False, server_default=""),
        sa.Column("source_type", _STR(50), nullable=False, server_default="unknown"),
        sa.Column("estimated_reach", _STR(30), nullable=False, server_default="unknown"),
        sa.Column("editorial_standards", _STR(20), nullable=False, server_default="unknown"),
        sa.Column("known_political_lean", _STR(30), nullable=False, server_default="unknown"),
        sa.Column("credibility_weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("reach_weight", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("rationale", sa.Text, nullable=False, server_default=""),
        sa.Column("requires_human_review", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("human_review_reason", sa.Text, nullable=False, server_default=""),
        sa.Column("scored_by", _STR(20), nullable=False, server_default="llm"),
        sa.Column("scored_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", _TS, nullable=False, server_default=sa.text("now()")),
    )
    op.create_unique_constraint(
        "uq_source_credibility_org_source",
        "source_credibility",
        ["org_id", "source_identifier"],
    )
    op.create_index("ix_source_credibility_org_id", "source_credibility", ["org_id"])
    op.create_index(
        "ix_source_credibility_requires_review",
        "source_credibility", ["requires_human_review"],
    )
    op.execute("""
        CREATE POLICY source_credibility_org_isolation ON source_credibility
        USING (org_id = current_setting('app.current_org_id')::uuid)
    """)
    op.execute("ALTER TABLE source_credibility ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE source_credibility FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for table in [
        "source_credibility",
        "district_patterns",
        "scheme_patterns",
        "sentiment_signals",
        "analyzed_mentions",
        "relevant_mentions",
        "raw_mentions",
        "theme_taxonomy",
    ]:
        policy_name = f"{table}_org_isolation"
        op.execute(f"DROP POLICY IF EXISTS {policy_name} ON {table}")
        op.drop_table(table)
