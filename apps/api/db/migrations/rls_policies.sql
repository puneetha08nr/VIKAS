-- RLS Policies for Vikas
-- Run this once after the initial schema migration.
-- The application sets app.current_org_id at the start of every request session.
-- Superusers/migration roles bypass RLS automatically.

-- ── organizations ────────────────────────────────────────────────────────────
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_self ON organizations
    USING (id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (id = current_setting('app.current_org_id')::uuid);

-- ── keywords ─────────────────────────────────────────────────────────────────
ALTER TABLE keywords ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON keywords
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── keyword_clusters ──────────────────────────────────────────────────────────
ALTER TABLE keyword_clusters ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON keyword_clusters
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── opportunities ─────────────────────────────────────────────────────────────
ALTER TABLE opportunities ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON opportunities
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── content_items ─────────────────────────────────────────────────────────────
ALTER TABLE content_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON content_items
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── content_reviews ───────────────────────────────────────────────────────────
ALTER TABLE content_reviews ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON content_reviews
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── competitors ───────────────────────────────────────────────────────────────
ALTER TABLE competitors ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON competitors
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── competitor_content ────────────────────────────────────────────────────────
ALTER TABLE competitor_content ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON competitor_content
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── trend_signals ─────────────────────────────────────────────────────────────
ALTER TABLE trend_signals ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON trend_signals
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── knowledge_chunks ──────────────────────────────────────────────────────────
ALTER TABLE knowledge_chunks ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON knowledge_chunks
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── brand_voice ───────────────────────────────────────────────────────────────
ALTER TABLE brand_voice ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON brand_voice
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── preferences ───────────────────────────────────────────────────────────────
ALTER TABLE preferences ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON preferences
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── agent_runs ────────────────────────────────────────────────────────────────
ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON agent_runs
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- ── pipeline_runs ─────────────────────────────────────────────────────────────
ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_isolation ON pipeline_runs
    USING (org_id = current_setting('app.current_org_id')::uuid)
    WITH CHECK (org_id = current_setting('app.current_org_id')::uuid);

-- prompts has no org_id — no RLS needed.
