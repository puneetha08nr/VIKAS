// Mock data for non-Keywords pages, derived from CLAUDE.md schema.

// ---- CONTENT ITEMS ----
const CONTENT_ITEMS = [
  { id: "ct1", title: "How AI agents are reshaping marketing automation in 2026", format: "article",  status: "review",    keyword: "ai marketing platform",     wordCount: 2400, brandVoice: 0.92, seo: 0.88, agent: "article_writer",   updatedAt: "12m ago",  author: "AR" },
  { id: "ct2", title: "5 prompts to get a 10x better content brief from your team", format: "linkedin", status: "review",    keyword: "ai writing assistant",      wordCount: 280,  brandVoice: 0.86, seo: null, agent: "linkedin_agent",   updatedAt: "38m ago",  author: "AR" },
  { id: "ct3", title: "The marketer's guide to retrieval-augmented generation",     format: "article",  status: "approved",  keyword: "rag for marketers",          wordCount: 3100, brandVoice: 0.94, seo: 0.91, agent: "article_writer",   updatedAt: "2h ago",   author: "RG" },
  { id: "ct4", title: "Weekly briefing: brand voice across 6 channels",             format: "newsletter", status: "draft",    keyword: "brand voice generator",      wordCount: 920,  brandVoice: 0.78, seo: null, agent: "newsletter_agent", updatedAt: "4h ago",   author: "AR" },
  { id: "ct5", title: "Threadable: why your competitor analysis is already stale",  format: "twitter",  status: "review",    keyword: "competitor content analysis",wordCount: 540,  brandVoice: 0.71, seo: null, agent: "twitter_agent",    updatedAt: "1d ago",   author: "AR" },
  { id: "ct6", title: "Lead magnet: AI marketing readiness checklist (PDF)",        format: "lead_magnet", status: "approved", keyword: "ai marketing platform",      wordCount: 1800, brandVoice: 0.89, seo: 0.84, agent: "lead_magnet_agent",updatedAt: "2d ago",   author: "RG" },
  { id: "ct7", title: "60s explainer: from keyword to publish",                     format: "video",    status: "draft",     keyword: "content workflow automation",wordCount: 220,  brandVoice: 0.81, seo: null, agent: "video_script",     updatedAt: "3d ago",   author: "AR" },
  { id: "ct8", title: "How we cut review queue time by 40% with brand_voice_keeper",format: "article",  status: "published", keyword: "brand voice generator",      wordCount: 2050, brandVoice: 0.96, seo: 0.93, agent: "article_writer",   updatedAt: "1w ago",   author: "RG" },
];

// ---- COMPETITORS ----
const COMPETITORS = [
  { id: "cp1", domain: "ahrefs.com",       lastCrawled: "1h ago", pages: 1842, threat: 86, overlap: 412, newPosts: 4 },
  { id: "cp2", domain: "semrush.com",      lastCrawled: "1h ago", pages: 2154, threat: 84, overlap: 388, newPosts: 6 },
  { id: "cp3", domain: "jasper.ai",        lastCrawled: "2h ago", pages:  720, threat: 72, overlap: 198, newPosts: 2 },
  { id: "cp4", domain: "copy.ai",          lastCrawled: "3h ago", pages:  640, threat: 64, overlap: 156, newPosts: 1 },
  { id: "cp5", domain: "writer.com",       lastCrawled: "5h ago", pages:  892, threat: 70, overlap: 174, newPosts: 3 },
  { id: "cp6", domain: "clearscope.io",    lastCrawled: "8h ago", pages:  310, threat: 58, overlap:  92, newPosts: 0 },
];

// ---- AGENT RUNS (Analytics) ----
const AGENT_RUNS = [
  { agent: "keyword_research",   tier: "fast",     runs: 142, success: 98.6, p50ms: 4200,  cost: 12.40, lastRun: "2m ago" },
  { agent: "keyword_validator",  tier: "fast",     runs: 318, success: 99.4, p50ms: 1800,  cost: 6.20,  lastRun: "5m ago" },
  { agent: "gap_analyzer",       tier: "standard", runs:  86, success: 96.5, p50ms: 12400, cost: 24.80, lastRun: "12m ago" },
  { agent: "article_planner",    tier: "standard", runs:  64, success: 95.3, p50ms: 18200, cost: 18.60, lastRun: "1h ago" },
  { agent: "article_writer",     tier: "standard", runs:  58, success: 91.4, p50ms: 42600, cost: 92.40, lastRun: "1h ago" },
  { agent: "linkedin_agent",     tier: "fast",     runs: 122, success: 99.2, p50ms: 3200,  cost: 4.80,  lastRun: "20m ago" },
  { agent: "competitor_monitor", tier: "fast",     runs:  48, success: 100.0, p50ms: 8200, cost: 2.10,  lastRun: "2h ago" },
  { agent: "trend_collector",    tier: "fast",     runs:  62, success: 98.4, p50ms: 5400,  cost: 3.30,  lastRun: "3h ago" },
  { agent: "rag_searcher",       tier: "fast",     runs: 412, success: 99.8, p50ms: 320,   cost: 0.80,  lastRun: "1m ago" },
  { agent: "brand_voice_keeper", tier: "fast",     runs: 198, success: 99.0, p50ms: 1200,  cost: 1.40,  lastRun: "8m ago" },
];

// ---- KNOWLEDGE DOCS ----
const KNOWLEDGE_DOCS = [
  { id: "d1", title: "Brand voice guidelines v3.pdf", type: "pdf", chunks: 124, ingestedAt: "Apr 28", size: "2.1 MB" },
  { id: "d2", title: "Q1 marketing strategy.docx",     type: "doc", chunks: 86,  ingestedAt: "Apr 22", size: "640 KB" },
  { id: "d3", title: "Customer interviews — 2026.md", type: "md",  chunks: 312, ingestedAt: "Apr 18", size: "1.8 MB" },
  { id: "d4", title: "Product positioning deck.pdf",   type: "pdf", chunks: 64,  ingestedAt: "Apr 10", size: "4.2 MB" },
  { id: "d5", title: "Competitive matrix.xlsx",        type: "sheet", chunks: 28, ingestedAt: "Apr 02", size: "320 KB" },
];

// ---- AUTO MODE OPPORTUNITIES ----
const OPPORTUNITIES = [
  { id: "o1", keyword: "ai email marketing automation", composite: 0.92, search: 0.88, gap: 0.94, trend: 0.91, engagement: 0.86, format: "article" },
  { id: "o2", keyword: "generative ai for marketing",   composite: 0.88, search: 0.92, gap: 0.81, trend: 0.94, engagement: 0.78, format: "article" },
  { id: "o3", keyword: "marketing ai agents",           composite: 0.84, search: 0.74, gap: 0.92, trend: 0.96, engagement: 0.72, format: "linkedin" },
  { id: "o4", keyword: "ai social caption generator",   composite: 0.79, search: 0.82, gap: 0.71, trend: 0.86, engagement: 0.74, format: "twitter" },
];

const INTEGRATIONS = [
  { id: "gsc",  name: "Google Search Console", status: "connected", account: "vikas.acme.co" },
  { id: "ga4",  name: "Google Analytics 4",    status: "connected", account: "GA4-72819203" },
  { id: "wp",   name: "WordPress",             status: "connected", account: "blog.acme.co" },
  { id: "ahrf", name: "DataForSEO",            status: "connected", account: "billing@acme.co" },
  { id: "lin",  name: "LinkedIn",              status: "connected", account: "Acme Inc." },
  { id: "tw",   name: "Twitter/X",             status: "disconnected", account: null },
  { id: "yt",   name: "YouTube",               status: "disconnected", account: null },
  { id: "slack",name: "Slack",                 status: "connected", account: "#marketing-ops" },
];

window.CONTENT_ITEMS = CONTENT_ITEMS;
window.COMPETITORS = COMPETITORS;
window.AGENT_RUNS = AGENT_RUNS;
window.KNOWLEDGE_DOCS = KNOWLEDGE_DOCS;
window.OPPORTUNITIES = OPPORTUNITIES;
window.INTEGRATIONS = INTEGRATIONS;
