"""initial schema

Revision ID: 6df9fe32fdcd
Revises:
Create Date: 2026-04-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6df9fe32fdcd"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Extensions ───────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── Enum types ───────────────────────────────────────────────────────────
    op.execute("""
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'keyword_status') THEN
        CREATE TYPE keyword_status AS ENUM ('raw', 'validated', 'clustered', 'archived');
    END IF;
END $$;
""")
    op.execute("""
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'search_intent') THEN
        CREATE TYPE search_intent AS ENUM
            ('informational', 'navigational', 'commercial', 'transactional');
    END IF;
END $$;
""")
    op.execute("""
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'opportunity_status') THEN
        CREATE TYPE opportunity_status AS ENUM ('new', 'in_progress', 'done', 'archived');
    END IF;
END $$;
""")
    op.execute("""
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'content_format') THEN
        CREATE TYPE content_format AS ENUM
            ('article', 'linkedin', 'twitter', 'newsletter', 'video_script', 'lead_magnet');
    END IF;
END $$;
""")
    op.execute("""
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'content_status') THEN
        CREATE TYPE content_status AS ENUM
            ('draft', 'review', 'approved', 'published', 'rejected');
    END IF;
END $$;
""")
    op.execute("""
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'preference_source') THEN
        CREATE TYPE preference_source AS ENUM ('approve', 'edit', 'reject');
    END IF;
END $$;
""")
    op.execute("""
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'agent_run_status') THEN
        CREATE TYPE agent_run_status AS ENUM ('running', 'success', 'failed', 'partial');
    END IF;
END $$;
""")
    op.execute("""
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'pipeline_run_status') THEN
        CREATE TYPE pipeline_run_status AS ENUM ('running', 'success', 'failed', 'partial');
    END IF;
END $$;
""")

    # ── organizations ────────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("settings", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    # ── keyword_clusters (no primary_keyword_id FK yet — added with ALTER below) ──
    op.create_table(
        "keyword_clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("intent", sa.Text(), nullable=False),
        sa.Column("primary_keyword_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_keyword_clusters_org_id", "keyword_clusters", ["org_id"])

    # ── keywords ─────────────────────────────────────────────────────────────
    op.create_table(
        "keywords",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword", sa.String(500), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("kd", sa.Float(), nullable=True),
        sa.Column("cpc", sa.Float(), nullable=True),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="raw"),
        sa.Column("source_agent", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["cluster_id"], ["keyword_clusters.id"],
                                name="fk_keywords_cluster_id", ondelete="SET NULL"),
    )
    op.create_index("ix_keywords_org_id", "keywords", ["org_id"])
    op.create_index("ix_keywords_cluster_id", "keywords", ["cluster_id"])

    # Now safe to add the circular FK from keyword_clusters → keywords
    op.create_foreign_key(
        "fk_keyword_clusters_primary_keyword_id",
        "keyword_clusters", "keywords",
        ["primary_keyword_id"], ["id"],
        ondelete="SET NULL",
    )

    # ── opportunities ────────────────────────────────────────────────────────
    op.create_table(
        "opportunities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("keyword_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("search_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("competitive_gap_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("trend_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("engagement_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("composite_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="new"),
        sa.Column("format_fit_scores", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["keyword_id"], ["keywords.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_opportunities_org_id", "opportunities", ["org_id"])
    op.create_index("ix_opportunities_keyword_id", "opportunities", ["keyword_id"])
    op.create_index("ix_opportunities_composite_score", "opportunities", ["composite_score"])

    # ── content_items ────────────────────────────────────────────────────────
    op.create_table(
        "content_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("format", sa.Text(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),
        sa.Column("brand_voice_score", sa.Float(), nullable=True),
        sa.Column("seo_score", sa.Float(), nullable=True),
        sa.Column("published_url", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_content_items_org_id", "content_items", ["org_id"])
    op.create_index("ix_content_items_opportunity_id", "content_items", ["opportunity_id"])
    op.create_index("ix_content_items_status", "content_items", ["status"])

    # ── content_reviews ──────────────────────────────────────────────────────
    op.create_table(
        "content_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dimension", sa.String(100), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("feedback_text", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["content_item_id"], ["content_items.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_content_reviews_org_id", "content_reviews", ["org_id"])
    op.create_index("ix_content_reviews_content_item_id", "content_reviews", ["content_item_id"])

    # ── competitors ──────────────────────────────────────────────────────────
    op.create_table(
        "competitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_competitors_org_id", "competitors", ["org_id"])

    # ── competitor_content ───────────────────────────────────────────────────
    op.create_table(
        "competitor_content",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("competitor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("threat_score", sa.Float(), nullable=True),
        sa.Column("keywords_overlap", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["competitor_id"], ["competitors.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_competitor_content_org_id", "competitor_content", ["org_id"])
    op.create_index("ix_competitor_content_competitor_id", "competitor_content", ["competitor_id"])

    # ── trend_signals ────────────────────────────────────────────────────────
    op.create_table(
        "trend_signals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("query", sa.String(500), nullable=False),
        sa.Column("momentum", sa.Float(), nullable=False, server_default="0"),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_trend_signals_org_id", "trend_signals", ["org_id"])
    op.create_index("ix_trend_signals_detected_at", "trend_signals", ["detected_at"])

    # ── knowledge_chunks ─────────────────────────────────────────────────────
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_doc", sa.String(500), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("embedding", sa.Text(), nullable=True),  # replaced by vector below
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    # Replace placeholder Text column with the real vector type
    op.execute("ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector(1536) USING NULL")
    op.create_index("ix_knowledge_chunks_org_id", "knowledge_chunks", ["org_id"])

    # ── brand_voice ──────────────────────────────────────────────────────────
    op.create_table(
        "brand_voice",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tone", sa.String(255), nullable=False, server_default=""),
        sa.Column("vocabulary", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("banned_phrases", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'[]'::jsonb")),
        sa.Column("style_rules", postgresql.JSONB, nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("org_id", name="uq_brand_voice_org_id"),
    )

    # ── preferences ──────────────────────────────────────────────────────────
    op.create_table(
        "preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_preferences_org_id", "preferences", ["org_id"])

    # ── prompts (global — no org_id) ──────────────────────────────────────────
    op.create_table(
        "prompts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_prompts_agent_name", "prompts", ["agent_name"])
    op.create_index("ix_prompts_active", "prompts", ["active"])

    # ── agent_runs ───────────────────────────────────────────────────────────
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_runs_org_id", "agent_runs", ["org_id"])
    op.create_index("ix_agent_runs_agent_name", "agent_runs", ["agent_name"])
    op.create_index("ix_agent_runs_started_at", "agent_runs", ["started_at"])

    # ── pipeline_runs ────────────────────────────────────────────────────────
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("pipeline_name", sa.String(100), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_pipeline_runs_org_id", "pipeline_runs", ["org_id"])
    op.create_index("ix_pipeline_runs_pipeline_name", "pipeline_runs", ["pipeline_name"])
    op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", ["started_at"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("pipeline_runs")
    op.drop_table("agent_runs")
    op.drop_table("prompts")
    op.drop_table("preferences")
    op.drop_table("brand_voice")
    op.drop_table("knowledge_chunks")
    op.drop_table("trend_signals")
    op.drop_table("competitor_content")
    op.drop_table("competitors")
    op.drop_table("content_reviews")
    op.drop_table("content_items")
    op.drop_table("opportunities")
    # Drop the circular FK before dropping keywords / keyword_clusters
    op.drop_constraint("fk_keyword_clusters_primary_keyword_id", "keyword_clusters",
                       type_="foreignkey")
    op.drop_table("keywords")
    op.drop_table("keyword_clusters")
    op.drop_table("organizations")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS pipeline_run_status CASCADE")
    op.execute("DROP TYPE IF EXISTS agent_run_status CASCADE")
    op.execute("DROP TYPE IF EXISTS preference_source CASCADE")
    op.execute("DROP TYPE IF EXISTS content_status CASCADE")
    op.execute("DROP TYPE IF EXISTS content_format CASCADE")
    op.execute("DROP TYPE IF EXISTS opportunity_status CASCADE")
    op.execute("DROP TYPE IF EXISTS search_intent CASCADE")
    op.execute("DROP TYPE IF EXISTS keyword_status CASCADE")
