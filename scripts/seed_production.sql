-- ============================================================
-- Vikas Production Seed Script
-- Table creation + demo content data
-- Run: psql -U vikas -d vikas -f scripts/seed_production.sql
-- Safe to run multiple times (IF NOT EXISTS + ON CONFLICT DO NOTHING)
-- ============================================================

-- Step 1: Set RLS context for dev org
SET app.current_org_id = '00000000-0000-0000-0000-000000000001';


-- Step 2: Create new tables (IF NOT EXISTS)
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

-- Step 3: Insert demo data (ON CONFLICT DO NOTHING = safe to re-run)
INSERT INTO public.organizations VALUES ('00000000-0000-0000-0000-000000000001', 'Vikas Dev Org', 'vikas-dev', '{}', '2026-05-05 06:30:14.686067+00', '2026-05-05 06:30:14.686067+00', NULL) ON CONFLICT DO NOTHING;
INSERT INTO public.keywords VALUES ('cccccccc-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'ai marketing tools', 5400, 38, 3.2, NULL, 'validated', 'keyword_validator', '2026-05-05 06:51:29.356045+00', '2026-05-05 06:51:29.356045+00', 'commercial', NULL, NULL, 'llm_estimate') ON CONFLICT DO NOTHING;
INSERT INTO public.opportunities VALUES ('dddddddd-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'cccccccc-0000-0000-0000-000000000001', 'keyword_research', 7.5, 6.8, 8.2, 6, 7.1, 'in_progress', '{"article": 8.5, "twitter": 3.5, "linkedin": 7.0}', '2026-05-05 06:51:29.356045+00') ON CONFLICT DO NOTHING;
INSERT INTO public.article_plans VALUES ('c61909e2-dc92-4f39-a36f-402553e5071b', '00000000-0000-0000-0000-000000000001', 'dddddddd-0000-0000-0000-000000000001', 'ai marketing tools', 'Maximizing Your Marketing Efficiency: A Comprehensive Guide to AI Marketing Tools', 'Explore the potential of artificial intelligence in marketing and uncover the top AI marketing tools that can streamline your operations for increased ROI.', '[{"h2": "The Revolution of AI in Marketing", "h3s": [], "detail": "Delve into the evolution of AI in marketing, its impact on modern teams, and why it''s essential for staying competitive."}, {"h2": "Understanding AI Marketing Tools", "h3s": [], "detail": "Break down the concept of AI marketing tools, their capabilities, and benefits for businesses."}, {"h2": "Top AI Marketing Tools: A Closer Look", "h3s": ["Content Creation Tools", "SEO Tools", "Predictive Analytics Tools", "Automated Advertising Platforms"], "detail": "Examine popular AI marketing tools, evaluating their pros, cons, and pricing structures to help you make informed decisions."}, {"h2": "Implementing AI Marketing Tools for Success", "h3s": [], "detail": "Practical tips and strategies on how to effectively integrate AI marketing tools into your marketing strategy."}]', 1800, 'Understanding and harnessing the power of AI marketing tools', 'Experience the Future Now', 'written', '2026-05-07 05:01:36.017439+00', '2026-05-07 05:01:36.017439+00') ON CONFLICT DO NOTHING;
INSERT INTO public.article_plans VALUES ('d2b3f576-033c-4548-8764-02a99aa8e916', '00000000-0000-0000-0000-000000000001', 'dddddddd-0000-0000-0000-000000000001', 'ai marketing tools', 'Maximizing Your Marketing Strategy with Top AI Tools in 2023', 'Explore the best AI marketing tools that can revolutionize your strategy, boost ROI and streamline your workflow.', '[{"h2": "The Rise of AI in Marketing: Why It Matters", "h3s": [], "detail": "Understand the impact and significance of AI tools on modern marketing strategies."}, {"h2": "Top 10 AI Marketing Tools for Businesses", "h3s": ["Content Creation Tools", "SEO Tools", "Analytics & Reporting", "Automated Advertising"], "detail": "Review each tool, its features, benefits, and potential drawbacks, along with pricing information."}, {"h2": "Implementing AI Marketing Tools: A Step-by-Step Guide", "h3s": [], "detail": "Provide practical advice on how to integrate these tools into existing marketing strategies."}]', 1800, 'Practical guide for businesses of all sizes', 'Start a free trial today', 'planned', '2026-05-07 06:27:08.414462+00', '2026-05-07 06:27:08.414462+00') ON CONFLICT DO NOTHING;
INSERT INTO public.article_plans VALUES ('a78d41b8-fba0-4d09-8acd-145042175767', '00000000-0000-0000-0000-000000000001', 'dddddddd-0000-0000-0000-000000000001', 'ai marketing tools', 'Maximizing Your Marketing Efforts with Top AI Tools: A Comprehensive Guide for Modern Marketers', 'Explore the benefits of AI marketing tools and learn how to select the best ones for your team in this comprehensive guide.', '[{"h2": "Understanding the Power of AI in Modern Marketing", "h3s": [], "detail": "Explore the potential of AI and its impact on modern marketing strategies."}, {"h2": "Identifying Your Business Needs for AI Tools", "h3s": ["Key Performance Indicators (KPIs) to Consider", "Aligning AI Tools with Marketing Goals"], "detail": "Discuss how to assess your business requirements for selecting AI marketing tools."}, {"h2": "Top AI Marketing Tools: A Comparative Analysis", "h3s": ["Content Creation", "SEO Tools", "Social Media Management", "Email Automation", "Predictive Analytics"], "detail": "Review popular AI marketing tools in the market and evaluate their pros, cons, and pricing."}, {"h2": "Implementing AI Marketing Tools for Maximum Results", "h3s": ["Data Integration and Management", "Training AI Algorithms", "Monitoring Performance"], "detail": "Provide practical tips and strategies for successfully integrating AI tools into your marketing stack."}]', 1800, 'Practical step-by-step guide for choosing AI marketing tools', 'Browse AI Marketing Tools Now', 'planned', '2026-05-07 06:33:00.940142+00', '2026-05-07 06:33:00.940142+00') ON CONFLICT DO NOTHING;
INSERT INTO public.article_plans VALUES ('5012f1b1-1e2d-4af5-9158-07edbb4e8695', '00000000-0000-0000-0000-000000000001', 'dddddddd-0000-0000-0000-000000000001', 'ai marketing tools', 'Maximizing Your Marketing Efforts: A Comprehensive Guide to AI Marketing Tools', 'Explore the transformative power of AI marketing tools and learn how to integrate them effectively into your strategy for enhanced ROI.', '[{"h2": "Understanding the Impact of AI on Modern Marketing", "h3s": [], "detail": "Delve into the significance of AI in marketing, its benefits, and how it enhances marketing efficiency."}, {"h2": "The Top 10 AI Marketing Tools Transforming Industries", "h3s": ["Content Creation AI Tools", "AI SEO Tools", "Predictive Analytics Solutions", "Chatbot and Automation Platforms"], "detail": "Review and compare each tool based on features, pricing, and case studies demonstrating their effectiveness in real-world scenarios."}, {"h2": "Choosing the Right Tool for Your Marketing Strategy", "h3s": [], "detail": "Provide actionable advice on selecting AI marketing tools that cater to your unique needs and objectives."}, {"h2": "Best Practices for Integrating AI into Your Marketing Stack", "h3s": [], "detail": "Offer guidance on seamlessly integrating AI marketing tools with existing systems, data management, and team collaboration."}]', 1800, 'Practical guide for marketers seeking to leverage AI', 'Transform Your Marketing Strategy Today', 'planned', '2026-05-07 06:41:06.551357+00', '2026-05-07 06:41:06.551357+00') ON CONFLICT DO NOTHING;
INSERT INTO public.article_plans VALUES ('e9dbb0f9-fc34-4f50-8ad2-aa866c1639a5', '00000000-0000-0000-0000-000000000001', 'dddddddd-0000-0000-0000-000000000001', 'ai marketing tools', 'Mastering AI Marketing Tools: A Comprehensive Guide for 2022', 'Explore the latest AI marketing tools that are revolutionizing digital strategies and driving success.', '[{"h2": "The Top 10 AI Marketing Tools for Modern people", "h3s": ["Content Creation", "SEO Optimization", "Social Media Management", "Email Marketing", "Predictive Analytics"], "detail": "Review each tool with an in-depth analysis of features, pricing, and benefits."}, {"h2": "Understanding AI Marketing Tools", "h3s": [], "detail": "Define AI marketing tools, discuss their potential impact on businesses, and explain why adopting them is crucial."}, {"h2": "Implementing AI Marketing Tools in Your Business Strategy", "h3s": [], "detail": "Offer practical tips and best practices for selecting, integrating, and maximizing the effectiveness of AI marketing tools."}, {"h2": "Future Trends in AI Marketing Tools", "h3s": [], "detail": "Discuss emerging trends and technologies that will shape the future of AI marketing."}, {"h2": "understanding GCC market", "h3s": [], "detail": ""}, {"h2": "today''s market value for AI.", "h3s": [], "detail": ""}, {"h2": "suggestion of tools less than 50$/month", "h3s": [], "detail": ""}]', 1800, 'Guide to leveraging artificial intelligence for enhanced marketing', 'Experience these tools firsthand with a free trial', 'written', '2026-05-07 07:20:39.492148+00', '2026-05-12 12:18:07.992367+00') ON CONFLICT DO NOTHING;
INSERT INTO public.articles VALUES ('9d57933f-9f64-4f6c-aa3b-c0e94df45f08', '00000000-0000-0000-0000-000000000001', 'c61909e2-dc92-4f39-a36f-402553e5071b', NULL, 'Maximizing Your Marketing Efficiency: A Comprehensive Guide to AI Marketing Tools', '<h2>The Revolution of AI in Marketing</h2>
INSERT INTO public.articles VALUES ('f2279bed-b75b-4f9f-82d1-ca98cb24a687', '00000000-0000-0000-0000-000000000001', 'e9dbb0f9-fc34-4f50-8ad2-aa866c1639a5', NULL, 'Mastering AI Marketing Tools: A Comprehensive Guide for 2022', '<h2>Understanding AI Marketing Tools</h2>
INSERT INTO public.articles VALUES ('c859f667-8d0a-41b1-a9b2-c8cc2e4f4285', '00000000-0000-0000-0000-000000000001', 'e9dbb0f9-fc34-4f50-8ad2-aa866c1639a5', NULL, 'Mastering AI Marketing Tools: A Comprehensive Guide for 2022', '<h2>The Top 10 AI Marketing Tools for Modern people</h2>
INSERT INTO public.articles VALUES ('1a064e99-e3d3-41e8-ab72-85c17b76b1a4', '00000000-0000-0000-0000-000000000001', 'e9dbb0f9-fc34-4f50-8ad2-aa866c1639a5', NULL, 'Mastering AI Marketing Tools: A Comprehensive Guide for 2022', '<h2>The Top 10 AI Marketing Tools for Modern people</h2>
INSERT INTO public.knowledge_chunks VALUES ('804dd2ee-535a-4e38-91f8-a6037c835eca', '00000000-0000-0000-0000-000000000001', 'agent_capabilities', '# Vikas Agent Capabilities
INSERT INTO public.knowledge_chunks VALUES ('f928736d-f118-44d4-b0aa-61d13f3096c1', '00000000-0000-0000-0000-000000000001', 'agent_capabilities', 'clear CTA. Reads from full article for newsletter depth. ### video_script_agent Converts articles into video scripts with scenes, narration, visuals, and B-roll suggestions. Structured for 3-5 minute educational videos. ### lead_magnet_agent Creates downloadable lead magnets — checklists, ebooks, templates — from keyword topics. Each item is actionable and immediately usable.
INSERT INTO public.knowledge_chunks VALUES ('f1dc6605-45b1-4550-831f-a29e942f3d4c', '00000000-0000-0000-0000-000000000001', 'faq', '# Vikas FAQ
INSERT INTO public.knowledge_chunks VALUES ('708d2617-8d7d-4397-bd1e-e179f6ebaa09', '00000000-0000-0000-0000-000000000001', 'faq', '(via API credentials) - DALL-E 3 for image generation - Slack for team notifications - ZeptoMail/SMTP for email notifications ## Is my data secure? Yes. Every organization''s data is completely isolated using Row Level Security (RLS) at the PostgreSQL level. No data from one organization can be seen by another.
INSERT INTO public.knowledge_chunks VALUES ('63466b6a-a339-4199-b9e3-262a7d896735', '00000000-0000-0000-0000-000000000001', 'how_it_works', '# How Vikas Works
INSERT INTO public.knowledge_chunks VALUES ('790f4b66-21b0-45e7-8e72-9ce8395ec409', '00000000-0000-0000-0000-000000000001', 'how_it_works', 'your edits through the preference_learner agent — the 11th article is noticeably better than the 1st. ### Step 9: Publishing Approved articles go to wordpress_publisher which pushes them to your WordPress site via the REST API. Social posts can be published to their respective platforms once API credentials are configured.
INSERT INTO public.linkedin_posts VALUES ('2ab51127-8086-475c-83b3-ba06ae57fe0e', '00000000-0000-0000-0000-000000000001', '9d57933f-9f64-4f6c-aa3b-c0e94df45f08', NULL, '{"post_text": "Did you know that over 80% of PRIMARY_ai marketing teams are using the wrong tools for their specific needs?
INSERT INTO public.linkedin_posts VALUES ('58190016-dcd9-4752-b58c-ef7ffb8d53b1', '00000000-0000-0000-0000-000000000001', 'f2279bed-b75b-4f9f-82d1-ca98cb24a687', NULL, '{"post_text": "In the rapidly evolving world of AI marketing, one tool isn''t enough to stay ahead.
INSERT INTO public.newsletters VALUES ('fa0af935-7ac5-46d9-87ce-53b8a8309139', '00000000-0000-0000-0000-000000000001', '9d57933f-9f64-4f6c-aa3b-c0e94df45f08', NULL, 'Maximizing Your Marketing Efficiency: A Comprehensive Guide to AI Marketing Tools', '', 'draft', '2026-05-07 07:23:38.115367+00', '2026-05-07 07:23:38.115367+00', '{}', 'Boost productivity and save valuable time. Discover the best AI marketing tools now!', '{
INSERT INTO public.newsletters VALUES ('a73130cc-ca4d-401f-848b-0cd027089337', '00000000-0000-0000-0000-000000000001', '9d57933f-9f64-4f6c-aa3b-c0e94df45f08', NULL, 'Maximizing Your Marketing Efficiency: A Comprehensive Guide to AI Marketing Tools', '', 'draft', '2026-05-07 07:29:06.728311+00', '2026-05-07 07:29:06.728311+00', '{}', 'Discover the secret weapons most teams aren''t using yet.', '{
INSERT INTO public.prompts VALUES ('5a44221a-fa81-4edd-8a38-fb98a4417c40', 'keyword_research', 1, 'You are a keyword research specialist. Generate 10 related keywords for: SEED_KEYWORD
INSERT INTO public.prompts VALUES ('255fb691-8503-46b8-9148-185a5b71cf6e', 'article_writer', 1, 'You are writing a high-quality, SEO-optimized article that ranks well and genuinely
INSERT INTO public.prompts VALUES ('963c9a88-3e7d-4dcc-95e4-bc9c72afb8b4', 'linkedin_agent', 1, 'You are writing a LinkedIn post that drives engagement and positions the author as
INSERT INTO public.prompts VALUES ('08d1ea3b-95a4-4808-adbb-abde29a647ea', 'keyword_validator', 1, 'Evaluate these keywords for SEO content creation.
INSERT INTO public.prompts VALUES ('7af364ce-e2b3-431e-bc8e-2e718be4ee92', 'article_planner', 1, 'You are creating a detailed article outline optimized for both SEO and reader value.
INSERT INTO public.prompts VALUES ('e9a3e74f-655a-487a-a514-c2b282f44d0c', 'keyword_research', 2, 'You are a keyword research specialist. Generate 10 related keywords for: SEED_KEYWORD
INSERT INTO public.prompts VALUES ('68e6752c-aac0-4ab2-bf24-33b54f7e1e60', 'keyword_validator', 2, 'Evaluate these keywords for SEO content creation.
INSERT INTO public.prompts VALUES ('8b21f94b-db1a-4dc0-b1e8-e62f9a475607', 'article_writer', 2, 'You are writing one section of an SEO-optimized article. Write only the HTML body of this section.
INSERT INTO public.prompts VALUES ('85c8d7e0-5a3c-4014-883c-71935f32c2ed', 'video_script_agent', 1, 'You are writing a video script for a short-form educational marketing video (3-5 minutes).
INSERT INTO public.prompts VALUES ('258c4633-0305-4c1c-a283-bad301ad8983', 'lead_magnet_agent', 1, 'You are creating a high-value lead magnet that captures email addresses by solving a specific problem.
INSERT INTO public.prompts VALUES ('8cf6ea6f-c1cc-429e-ac60-ee2cdfbaee53', 'newsletter_agent', 1, 'You are writing a marketing email newsletter that educates subscribers and drives clicks.
INSERT INTO public.prompts VALUES ('1033006f-30aa-4e9e-9b4a-05802fd4063d', 'brand_voice_keeper', 1, 'You are enforcing brand voice guidelines during content review. Your job is to identify
INSERT INTO public.prompts VALUES ('ac7aa148-c23b-4a33-9de4-f04375774fa4', 'keyword_research', 3, 'You are a keyword research specialist. Generate 10 related keywords for: SEED_KEYWORD
INSERT INTO public.prompts VALUES ('2a586306-9938-4d1a-ba16-441feab2529a', 'keyword_validator', 3, 'Evaluate these keywords for SEO content creation.
INSERT INTO public.prompts VALUES ('73dd7c1d-277d-4e25-b619-883451b794fb', 'article_planner', 2, 'You are creating a detailed article outline optimized for both SEO and reader value.
INSERT INTO public.prompts VALUES ('a18da8ca-7e2c-483b-b322-f81ce1fa4932', 'brand_voice_keeper', 2, 'You are enforcing brand voice guidelines during content review. Your job is to identify
INSERT INTO public.prompts VALUES ('5972e725-51b3-46af-923e-6be30791b7d8', 'article_planner', 3, 'You are creating a detailed article outline optimized for both SEO and reader value.
INSERT INTO public.prompts VALUES ('11da6f09-49b2-43d9-aff7-6066b1ff0f57', 'article_writer', 3, 'You are writing one section of an SEO-optimized article. Write only the HTML body of this section.
INSERT INTO public.prompts VALUES ('de0acf09-a03c-4542-8c22-5aa9e017a154', 'linkedin_agent', 2, 'You are writing a LinkedIn post that drives engagement and positions the author as
INSERT INTO public.prompts VALUES ('c9eb4ba4-01cf-490c-9cde-aac785db0c87', 'linkedin_agent', 3, 'You are writing a LinkedIn post that drives engagement and positions the author as
INSERT INTO public.prompts VALUES ('da03ae05-bff3-41c8-b3fa-75f633ec47c2', 'video_script_agent', 2, 'You are writing a video script for a short-form educational marketing video (3-5 minutes).
INSERT INTO public.prompts VALUES ('847078d2-0d2a-42f5-9bf7-16bc5e967672', 'lead_magnet_agent', 2, 'You are creating a high-value lead magnet that captures email addresses by solving a specific problem.
INSERT INTO public.prompts VALUES ('9983ca2b-1607-4e3b-91c9-6683bd4b150a', 'image_creator_agent', 1, 'You are writing a detailed image generation prompt for a marketing visual.
INSERT INTO public.prompts VALUES ('10b73136-a928-45b9-bcf8-1d4981450363', 'image_creator_agent', 2, 'You are writing a detailed image generation prompt for a marketing visual.
INSERT INTO public.prompts VALUES ('0d6ccd37-d74e-4f85-9b19-25afd4bd2a4d', 'newsletter_agent', 2, 'You are writing a marketing email newsletter that educates subscribers and drives clicks.
INSERT INTO public.prompts VALUES ('ccca2ad2-1992-4b3a-a386-80273e10d601', 'twitter_agent', 1, 'You are writing a Twitter/X thread that drives engagement and grows an audience.
INSERT INTO public.prompts VALUES ('b3307272-24a4-4055-a815-80d93a9cf3a7', 'twitter_agent', 2, 'You are writing a Twitter/X thread that drives engagement and grows an audience.
INSERT INTO public.prompts VALUES ('c2a683bb-3391-45dd-b1cf-40a1d2266b55', 'brand_voice_keeper', 3, 'You are enforcing brand voice guidelines during content review. Your job is to identify
INSERT INTO public.twitter_threads VALUES ('b68dd29b-57d7-4e90-88f2-d2ca341322dd', '00000000-0000-0000-0000-000000000001', '9d57933f-9f64-4f6c-aa3b-c0e94df45f08', NULL, '["{\"tweets\": [\"1/ PRIMARY_ai marketing tools drive 50% of leads. Time to level up your game!\", \"2/ Here''s the kicker: manual strategies are losing ground.\", \"3/ Automation is the future, and it''s here now. Embrace AI marketing tools.\", \"4/ Why should you care? Because automation saves time & increases efficiency.\", \"5/ Tip 1: Use chatbots for customer support.\", \"6/ Tip 2: Implement AI-powered email campaigns.\", \"7/ Tip 3: Optimize your content with smart SEO.\", \"8/ Tip 4: Analyze data to make data-driven decisions.\", \"9/ The takeaway: Upgrade to AI marketing tools now!\", \"10/ Follow for more tips on mastering PRIMARY_ai marketing tools OR check out this article: #aimarketing #seo\"], \"hashtags\": [\"aimarketing\", \"seo\"], \"estimated_reach_tier\": \"medium\"}"]', 0, 'draft', '2026-05-07 07:12:03.026664+00', '2026-05-07 07:12:03.026664+00', '{}', NULL) ON CONFLICT DO NOTHING;


-- Step 3: Stamp alembic to latest so migrations don't re-run
UPDATE alembic_version SET version_num = '99f280ffc5b3' WHERE TRUE;
INSERT INTO alembic_version (version_num)
SELECT '99f280ffc5b3' WHERE NOT EXISTS (SELECT 1 FROM alembic_version);

-- Re-enable triggers
SET session_replication_role = DEFAULT;

SELECT 'Seed complete' AS result;
