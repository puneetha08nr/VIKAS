# Vikas Agent Capabilities

## SEO Agents

### keyword_research
Finds 500+ related keywords for any seed topic using DataForSEO. Returns real search volumes, keyword difficulty, CPC, and search intent. Clusters keywords by intent automatically.

### keyword_validator
Filters raw keywords using hard rules and LLM judgment. Validates commercial viability, search intent, and competition level. Marks keywords as validated or archived.

### opportunity_scorer
Scores validated keywords across 4 dimensions — search volume, competitive gap, trend momentum, engagement potential. Combines into a composite score (0-10) and creates opportunities for high-scoring keywords.

### rank_tracker
Tracks your Google Search Console ranking positions for all validated keywords. Identifies quick wins (ranking 11-30, easy to push to page 1).

### gap_analyzer
Compares your rankings against competitors. Finds keywords where competitors rank but you don't — high-value content opportunities.

### trend_collector
Monitors trending topics from Google Trends, Reddit, Wikipedia. Assigns momentum scores to identify rising topics before they peak.

### site_auditor
Audits your entire site against all validated keywords. Shows which pages rank, which don't, and which need improvement.

### aeo_scanner
Scans for Answer Engine Optimization opportunities — featured snippets, People Also Ask boxes, AI overview appearances.

## Content Agents

### content_director
Orchestrates the full content pipeline for one opportunity. Triggers article_planner, article_writer, and all social agents in the right order.

### article_planner
Generates a structured SEO outline before writing. Produces title, meta description, H2 sections with details, H3 subsections, content angle, and CTA. Human can edit before writing starts.

### article_writer
Writes the full article section by section using the approved outline. Incorporates brand voice, knowledge base, and SEO requirements. Produces 1500-2000 word HTML articles.

### linkedin_agent
Creates LinkedIn posts optimized for engagement. Uses hook-body-CTA formula. Reads from article outline for efficiency (fewer tokens than reading full article).

### twitter_agent
Creates 10-tweet threads from article outlines. Numbered tweets with hook, value, and CTA. Optimized for engagement and thread readability.

### newsletter_agent
Creates email newsletters from full articles. Produces subject line, preview text, and HTML body with clear CTA. Reads from full article for newsletter depth.

### video_script_agent
Converts articles into video scripts with scenes, narration, visuals, and B-roll suggestions. Structured for 3-5 minute educational videos.

### lead_magnet_agent
Creates downloadable lead magnets — checklists, ebooks, templates — from keyword topics. Each item is actionable and immediately usable.

### image_creator_agent
Generates detailed DALL-E 3 image prompts for article featured images. Optionally calls the DALL-E API to produce the actual image.

## Knowledge Agents

### document_ingester
Ingests company documents (PDFs, Word docs, text files) into the knowledge base. Chunks and embeds them for RAG retrieval by article_writer.

### rag_searcher
Searches the knowledge base using vector similarity. Returns the most relevant chunks for any query. Used by article_writer to inject company-specific facts.

### brand_voice_keeper
Analyzes content against your brand voice guidelines. Scores tone consistency, vocabulary, sentence structure, and values alignment. Suggests corrections for violations.

### internal_link_finder
Finds internal linking opportunities between your articles. Suggests anchor text and improves site structure for SEO.

### wordpress_publisher
Publishes approved articles to WordPress via the REST API. Sets categories, tags, featured images, and publication status.

### ai_assistant
Answers marketing questions using your knowledge base (RAG). Can query your live data (keywords, articles, opportunities) and answer company-specific questions.

## Orchestration Agents

### auto_mode_engine
Runs the nightly pipeline at 2 AM UTC. Selects top opportunities, applies learned preferences, triggers content pipeline, notifies team.

### pipeline_orchestrator
Manages complex multi-step pipelines. Handles failures, retries, and partial completions gracefully.

### strategy_synthesizer
Generates weekly strategy reports by analyzing all your data — keyword trends, content performance, competitor activity, opportunity pipeline.

### preference_learner
Extracts patterns from your content feedback (approvals, edits, rejections). Updates the system prompt weekly so future content automatically matches your preferences.
