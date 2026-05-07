export type KeywordStatus = 'raw' | 'validated' | 'clustered' | 'archived' | 'pending_metrics'
export type KeywordIntent = 'commercial' | 'informational' | 'transactional' | 'navigational'
export type DataSource = 'dataforseo' | 'keywords_everywhere' | 'estimated' | 'pending' | 'llm_estimate'
export type RunStatus = 'running' | 'success' | 'failed' | 'partial'

export interface KeywordRow {
  id: string
  keyword: string
  volume: number | null
  kd: number | null
  cpc: number | null
  intent: KeywordIntent | null
  status: KeywordStatus
  data_source: DataSource
  reason: string | null
  source_agent: string
  source_run_id: string | null
  cluster_id: string | null
  created_at: string
  // Extended — present in mock data; populated by detail endpoint for real data
  position?: number | null
  prevPosition?: number | null
  contentCount?: number
  url?: string | null
  trend?: number[]
  cluster?: string
}

export interface KwCluster {
  id: string
  name: string
  color: string
}

export interface KeywordStats {
  total: number
  raw: number
  validated: number
  archived: number
  clustered?: number
  commercial: number
  informational: number
  opportunities?: number
  pending?: number
}

export interface KeywordPage {
  keywords: KeywordRow[]
  total: number
  limit: number
  offset: number
  page: number
  total_pages: number
}

export interface AgentRun {
  run_id: string
  id?: string
  agent_name: string
  status: RunStatus
  duration_ms: number | null
  tokens_in: number
  tokens_out: number
  cost_usd: number
  model_used?: string | null
  error: string | null
  started_at: string
  completed_at: string | null
}

export interface KeywordDetail extends KeywordRow {
  recent_runs: AgentRun[]
  content_count: number
  trend_data: number[]
}

// ── Opportunities ─────────────────────────────────────────────────────────────

export interface Opportunity {
  id: string
  keyword_id: string
  keyword: string
  source: string
  search_score: number | null
  competitive_gap_score: number | null
  trend_score: number | null
  engagement_score: number | null
  composite_score: number | null
  status: string
  created_at: string
}

// ── Content / Articles ────────────────────────────────────────────────────────

export type ArticleStatus = 'draft' | 'review' | 'approved' | 'published'

export interface Article {
  id: string
  org_id: string
  opportunity_id: string | null
  title: string
  body_html: string | null
  word_count: number | null
  keyword: string | null
  status: ArticleStatus
  published_url: string | null
  brand_voice_score: number | null
  seo_score: number | null
  created_at: string
}

export interface LinkedInPost {
  id: string
  article_id: string | null
  content: string | null
  hashtags: string[] | null
  status: string
  created_at: string
}

export interface TwitterThread {
  id: string
  article_id: string | null
  tweets: string[]
  tweet_count: number
  status: string
  created_at: string
}

export interface Newsletter {
  id: string
  article_id: string | null
  subject: string | null
  preview_text: string | null
  body_html: string | null
  status: string
  created_at: string
}

// ── Competitors ───────────────────────────────────────────────────────────────

export interface Competitor {
  id: string
  domain: string
  last_crawled_at: string | null
  threat_score?: number | null
  keyword_overlap?: number | null
}

export interface CompetitorContent {
  id: string
  competitor_id: string
  domain?: string
  url: string
  title: string | null
  word_count: number | null
  threat_score: number | null
  keywords_overlap: string[] | null
  created_at: string
}

// ── Video Jobs ────────────────────────────────────────────────────────────────

export type VideoJobStatus = 'pending_video' | 'video_ready' | 'published' | 'failed'

export interface VideoJob {
  id: string
  article_id: string | null
  title: string | null
  scene_count: number | null
  duration_seconds: number | null
  status: VideoJobStatus
  upload_url: string | null
  video_url: string | null
  notes: string | null
  created_at: string
}

// ── Strategy ──────────────────────────────────────────────────────────────────

export interface StrategyReport {
  id: string
  opportunities_analyzed: number
  recommendations: StrategyRecommendation[]
  summary: string | null
  status: string
  created_at: string
}

export interface StrategyRecommendation {
  priority: number
  action: string
  rationale?: string
  expected_impact?: 'high' | 'medium' | 'low'
}

export interface RankTracking {
  id: string
  keyword_id: string
  keyword: string
  position: number | null
  previous_position: number | null
  url: string | null
  checked_at: string
}

export interface AeoResult {
  id: string
  keyword_id: string
  keyword: string
  has_ai_overview: boolean
  has_featured_snippet: boolean
  paa_count: number
  checked_at: string
}

// ── Brand Voice & Settings ────────────────────────────────────────────────────

export interface BrandVoice {
  id: string
  tone: string | null
  vocabulary: string[] | null
  banned_phrases: string[] | null
  style_rules: Record<string, string> | null
}

export interface AutoModeSettings {
  enabled: boolean
  schedule_time: string
  seed_keywords: string[]
  max_daily_pipelines: number
}
