-- Create all new tables added by the remote pull
-- Run as vikas admin user

-- Topics
CREATE TABLE IF NOT EXISTS topics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    topic VARCHAR(500) NOT NULL,
    source VARCHAR(50) NOT NULL,
    score FLOAT NOT NULL DEFAULT 0.0,
    related_keywords JSONB NOT NULL DEFAULT '[]'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_topics_org_id ON topics(org_id);
ALTER TABLE topics ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='topics' AND policyname='topics_org_isolation') THEN
    CREATE POLICY topics_org_isolation ON topics USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- Article plans
CREATE TABLE IF NOT EXISTS article_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
    keyword VARCHAR(500) NOT NULL,
    title VARCHAR(500) NOT NULL DEFAULT '',
    meta_description TEXT NOT NULL DEFAULT '',
    outline JSONB NOT NULL DEFAULT '[]'::jsonb,
    word_count_target INT NOT NULL DEFAULT 1800,
    content_angle TEXT NOT NULL DEFAULT '',
    cta TEXT NOT NULL DEFAULT '',
    status VARCHAR(50) NOT NULL DEFAULT 'planned',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_article_plans_org_id ON article_plans(org_id);
ALTER TABLE article_plans ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='article_plans' AND policyname='article_plans_org_isolation') THEN
    CREATE POLICY article_plans_org_isolation ON article_plans USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- Articles
CREATE TABLE IF NOT EXISTS articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    article_plan_id UUID REFERENCES article_plans(id) ON DELETE SET NULL,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
    title VARCHAR(500) NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    word_count INT NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    published_url TEXT,
    wp_post_id INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_articles_org_id ON articles(org_id);
ALTER TABLE articles ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='articles' AND policyname='articles_org_isolation') THEN
    CREATE POLICY articles_org_isolation ON articles USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- LinkedIn posts
CREATE TABLE IF NOT EXISTS linkedin_posts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    article_id UUID REFERENCES articles(id) ON DELETE SET NULL,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
    content TEXT NOT NULL DEFAULT '',
    word_count INT NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_linkedin_posts_org_id ON linkedin_posts(org_id);
ALTER TABLE linkedin_posts ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='linkedin_posts' AND policyname='linkedin_posts_org_isolation') THEN
    CREATE POLICY linkedin_posts_org_isolation ON linkedin_posts USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- Twitter threads
CREATE TABLE IF NOT EXISTS twitter_threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    article_id UUID REFERENCES articles(id) ON DELETE SET NULL,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
    tweets JSONB NOT NULL DEFAULT '[]'::jsonb,
    tweet_count INT NOT NULL DEFAULT 0,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_twitter_threads_org_id ON twitter_threads(org_id);
ALTER TABLE twitter_threads ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='twitter_threads' AND policyname='twitter_threads_org_isolation') THEN
    CREATE POLICY twitter_threads_org_isolation ON twitter_threads USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- Newsletters
CREATE TABLE IF NOT EXISTS newsletters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    article_id UUID REFERENCES articles(id) ON DELETE SET NULL,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_newsletters_org_id ON newsletters(org_id);
ALTER TABLE newsletters ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='newsletters' AND policyname='newsletters_org_isolation') THEN
    CREATE POLICY newsletters_org_isolation ON newsletters USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- Lead magnets
CREATE TABLE IF NOT EXISTS lead_magnets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
    keyword VARCHAR(500) NOT NULL DEFAULT '',
    format VARCHAR(50) NOT NULL DEFAULT 'checklist',
    title VARCHAR(500) NOT NULL DEFAULT '',
    body JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_lead_magnets_org_id ON lead_magnets(org_id);
ALTER TABLE lead_magnets ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='lead_magnets' AND policyname='lead_magnets_org_isolation') THEN
    CREATE POLICY lead_magnets_org_isolation ON lead_magnets USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- Strategy reports
CREATE TABLE IF NOT EXISTS strategy_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    summary TEXT NOT NULL DEFAULT '',
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_strategy_reports_org_id ON strategy_reports(org_id);
ALTER TABLE strategy_reports ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='strategy_reports' AND policyname='strategy_reports_org_isolation') THEN
    CREATE POLICY strategy_reports_org_isolation ON strategy_reports USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- AEO results
CREATE TABLE IF NOT EXISTS aeo_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    keyword_id UUID REFERENCES keywords(id) ON DELETE CASCADE,
    keyword VARCHAR(500) NOT NULL DEFAULT '',
    ai_overview BOOLEAN NOT NULL DEFAULT false,
    featured_snippet BOOLEAN NOT NULL DEFAULT false,
    paa_count INT NOT NULL DEFAULT 0,
    organic_position INT,
    status VARCHAR(50) NOT NULL DEFAULT 'ok',
    aeo_score FLOAT NOT NULL DEFAULT 0.0,
    scanned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_aeo_results_org_id ON aeo_results(org_id);
ALTER TABLE aeo_results ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='aeo_results' AND policyname='aeo_results_org_isolation') THEN
    CREATE POLICY aeo_results_org_isolation ON aeo_results USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- Video jobs
CREATE TABLE IF NOT EXISTS video_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE SET NULL,
    script TEXT NOT NULL DEFAULT '',
    scenes JSONB NOT NULL DEFAULT '[]'::jsonb,
    broll_suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    upload_url TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'pending_video',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_video_jobs_org_id ON video_jobs(org_id);
ALTER TABLE video_jobs ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='video_jobs' AND policyname='video_jobs_org_isolation') THEN
    CREATE POLICY video_jobs_org_isolation ON video_jobs USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- Broll suggestions
CREATE TABLE IF NOT EXISTS broll_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    video_job_id UUID REFERENCES video_jobs(id) ON DELETE CASCADE,
    scene_text TEXT NOT NULL DEFAULT '',
    suggestions JSONB NOT NULL DEFAULT '[]'::jsonb,
    status VARCHAR(50) NOT NULL DEFAULT 'ok',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_broll_suggestions_org_id ON broll_suggestions(org_id);

-- Content feedback
CREATE TABLE IF NOT EXISTS content_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    content_type VARCHAR(100) NOT NULL,
    content_id UUID NOT NULL,
    action VARCHAR(50) NOT NULL,
    processed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_content_feedback_org_id ON content_feedback(org_id);
ALTER TABLE content_feedback ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='content_feedback' AND policyname='content_feedback_org_isolation') THEN
    CREATE POLICY content_feedback_org_isolation ON content_feedback USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- Preference summaries
CREATE TABLE IF NOT EXISTS preference_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    content_type VARCHAR(100) NOT NULL,
    approval_rate FLOAT NOT NULL DEFAULT 0.0,
    edit_rate FLOAT NOT NULL DEFAULT 0.0,
    rejection_rate FLOAT NOT NULL DEFAULT 0.0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_preference_summaries_org_id ON preference_summaries(org_id);
ALTER TABLE preference_summaries ENABLE ROW LEVEL SECURITY;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename='preference_summaries' AND policyname='preference_summaries_org_isolation') THEN
    CREATE POLICY preference_summaries_org_isolation ON preference_summaries USING (org_id = current_setting('app.current_org_id')::uuid);
  END IF;
END $$;

-- Stamp alembic to latest revision
UPDATE alembic_version SET version_num = 'f6a7b8c9d0e1';

SELECT 'Done - all new tables created' AS result;
