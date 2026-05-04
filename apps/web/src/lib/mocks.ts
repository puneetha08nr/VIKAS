import type { KeywordRow, KwCluster, KeywordStats } from "./types";

export const KW_CLUSTERS: KwCluster[] = [
  { id: "c1", name: "AI Content Generation", color: "#534AB7" },
  { id: "c2", name: "Marketing Automation", color: "#0EA5E9" },
  { id: "c3", name: "SEO Tools", color: "#10B981" },
  { id: "c4", name: "Brand Voice", color: "#F59E0B" },
  { id: "c5", name: "Competitor Intel", color: "#EF4444" },
];

function seededSeries(
  seed: number,
  n = 12,
  base = 1000,
  vol = 0.18
): number[] {
  let s = seed;
  const rand = () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };
  const out: number[] = [];
  let v = base * (0.85 + rand() * 0.3);
  for (let i = 0; i < n; i++) {
    v = Math.max(10, v * (1 + (rand() - 0.5) * vol));
    out.push(Math.round(v));
  }
  return out;
}

export const mockKeywords: KeywordRow[] = [
  { id: "k1",  keyword: "ai content generator",        cluster: "c1", intent: "commercial",     status: "clustered",  volume: 49500, kd: 7.8, cpc: 12.40, data_source: "dataforseo",   reason: "Strong commercial intent + reachable difficulty for our DR",   source_agent: "keyword_research", source_run_id: null, cluster_id: null, created_at: "2026-04-01", position: 6,  prevPosition: 9,  url: "/blog/ai-content-generator", contentCount: 3, trend: seededSeries(8,  12, 49500, 0.16) },
  { id: "k2",  keyword: "marketing automation tools",  cluster: "c2", intent: "commercial",     status: "clustered",  volume: 22100, kd: 7.1, cpc: 18.20, data_source: "dataforseo",   reason: "Already ranking page 1, defend & expand",                     source_agent: "gap_analyzer",      source_run_id: null, cluster_id: null, created_at: "2026-04-01", position: 3,  prevPosition: 4,  url: "/compare/automation",        contentCount: 4, trend: seededSeries(9,  12, 22100, 0.16) },
  { id: "k3",  keyword: "best ai writing assistant",   cluster: "c1", intent: "transactional",  status: "validated",  volume: 18100, kd: 6.4, cpc: 9.10,  data_source: "dataforseo",   reason: "High intent, gap_analyzer queued",                            source_agent: "auto_mode",         source_run_id: null, cluster_id: null, created_at: "2026-04-02", position: null, prevPosition: null, url: null, contentCount: 0, trend: seededSeries(10, 12, 18100, 0.16) },
  { id: "k4",  keyword: "seo content optimization",    cluster: "c3", intent: "informational",  status: "clustered",  volume: 8200,  kd: 5.2, cpc: 7.80,  data_source: "dataforseo",   reason: "Mid-funnel, good cluster anchor",                             source_agent: "keyword_research", source_run_id: null, cluster_id: null, created_at: "2026-04-02", position: 12, prevPosition: 10, url: "/guides/seo-optimization",   contentCount: 2, trend: seededSeries(11, 12, 8200,  0.16) },
  { id: "k5",  keyword: "brand voice generator",       cluster: "c4", intent: "commercial",     status: "validated",  volume: 5400,  kd: 4.5, cpc: 6.40,  data_source: "dataforseo",   reason: "Aligns with product feature, low competition",                source_agent: "auto_mode",         source_run_id: null, cluster_id: null, created_at: "2026-04-03", position: null, prevPosition: null, url: null, contentCount: 1, trend: seededSeries(12, 12, 5400,  0.16) },
  { id: "k6",  keyword: "competitor content analysis", cluster: "c5", intent: "commercial",     status: "validated",  volume: 4800,  kd: 5.8, cpc: 11.20, data_source: "dataforseo",   reason: "Bottom of funnel for ICP",                                    source_agent: "gap_analyzer",      source_run_id: null, cluster_id: null, created_at: "2026-04-03", position: null, prevPosition: null, url: null, contentCount: 0, trend: seededSeries(13, 12, 4800,  0.16) },
  { id: "k7",  keyword: "ai marketing platform",       cluster: "c2", intent: "transactional",  status: "clustered",  volume: 14800, kd: 7.3, cpc: 22.80, data_source: "dataforseo",   reason: "Brand-fit, defend top 10",                                    source_agent: "keyword_research", source_run_id: null, cluster_id: null, created_at: "2026-04-04", position: 8,  prevPosition: 7,  url: "/product",                   contentCount: 5, trend: seededSeries(14, 12, 14800, 0.16) },
  { id: "k8",  keyword: "automated keyword research",  cluster: "c3", intent: "informational",  status: "raw",        volume: 3600,  kd: 4.1, cpc: 5.20,  data_source: "llm_estimate", reason: "",                                                            source_agent: "trend_collector",   source_run_id: null, cluster_id: null, created_at: "2026-04-04", position: null, prevPosition: null, url: null, contentCount: 0, trend: seededSeries(15, 12, 3600,  0.16) },
  { id: "k9",  keyword: "content workflow automation", cluster: "c2", intent: "commercial",     status: "raw",        volume: 2900,  kd: 4.9, cpc: 8.40,  data_source: "llm_estimate", reason: "",                                                            source_agent: "gap_analyzer",      source_run_id: null, cluster_id: null, created_at: "2026-04-05", position: null, prevPosition: null, url: null, contentCount: 0, trend: seededSeries(16, 12, 2900,  0.16) },
  { id: "k10", keyword: "blog post generator ai",      cluster: "c1", intent: "transactional",  status: "clustered",  volume: 12100, kd: 6.7, cpc: 10.10, data_source: "dataforseo",   reason: "Improving, push to top 10",                                   source_agent: "auto_mode",         source_run_id: null, cluster_id: null, created_at: "2026-04-05", position: 14, prevPosition: 18, url: "/tools/blog-generator",      contentCount: 2, trend: seededSeries(17, 12, 12100, 0.16) },
  { id: "k11", keyword: "linkedin post automation",    cluster: "c2", intent: "commercial",     status: "validated",  volume: 6700,  kd: 5.4, cpc: 9.80,  data_source: "dataforseo",   reason: "Integration page can rank further",                           source_agent: "keyword_research", source_run_id: null, cluster_id: null, created_at: "2026-04-06", position: 9,  prevPosition: 11, url: "/integrations/linkedin",     contentCount: 1, trend: seededSeries(18, 12, 6700,  0.16) },
  { id: "k12", keyword: "rank tracking software",      cluster: "c3", intent: "commercial",     status: "clustered",  volume: 9900,  kd: 6.9, cpc: 14.30, data_source: "dataforseo",   reason: "Crowded SERP, but feature page exists",                       source_agent: "keyword_research", source_run_id: null, cluster_id: null, created_at: "2026-04-06", position: 22, prevPosition: 19, url: "/features/rank-tracker",     contentCount: 2, trend: seededSeries(19, 12, 9900,  0.16) },
  { id: "k13", keyword: "ai newsletter writer",        cluster: "c1", intent: "transactional",  status: "raw",        volume: 2400,  kd: 3.8, cpc: 5.90,  data_source: "llm_estimate", reason: "",                                                            source_agent: "auto_mode",         source_run_id: null, cluster_id: null, created_at: "2026-04-07", position: null, prevPosition: null, url: null, contentCount: 1, trend: seededSeries(20, 12, 2400,  0.16) },
  { id: "k14", keyword: "competitor backlink monitor", cluster: "c5", intent: "commercial",     status: "archived",   volume: 1900,  kd: 5.1, cpc: 12.10, data_source: "dataforseo",   reason: "Out of scope — backlinks not a Vikas feature",                source_agent: "gap_analyzer",      source_run_id: null, cluster_id: null, created_at: "2026-04-07", position: null, prevPosition: null, url: null, contentCount: 0, trend: seededSeries(21, 12, 1900,  0.16) },
  { id: "k15", keyword: "content gap analysis tool",   cluster: "c5", intent: "commercial",     status: "validated",  volume: 3300,  kd: 4.7, cpc: 9.20,  data_source: "dataforseo",   reason: "Direct product fit",                                          source_agent: "gap_analyzer",      source_run_id: null, cluster_id: null, created_at: "2026-04-08", position: null, prevPosition: null, url: null, contentCount: 0, trend: seededSeries(22, 12, 3300,  0.16) },
  { id: "k16", keyword: "ai brand voice training",     cluster: "c4", intent: "informational",  status: "raw",        volume: 880,   kd: 3.2, cpc: 4.10,  data_source: "llm_estimate", reason: "",                                                            source_agent: "trend_collector",   source_run_id: null, cluster_id: null, created_at: "2026-04-08", position: null, prevPosition: null, url: null, contentCount: 0, trend: seededSeries(23, 12, 880,   0.16) },
  { id: "k17", keyword: "ai social caption generator", cluster: "c1", intent: "transactional",  status: "raw",        volume: 4200,  kd: 4.3, cpc: 6.80,  data_source: "llm_estimate", reason: "",                                                            source_agent: "trend_collector",   source_run_id: null, cluster_id: null, created_at: "2026-04-09", position: null, prevPosition: null, url: null, contentCount: 0, trend: seededSeries(24, 12, 4200,  0.16) },
  { id: "k18", keyword: "marketing dashboard software",cluster: "c2", intent: "commercial",     status: "archived",   volume: 6100,  kd: 7.6, cpc: 15.40, data_source: "dataforseo",   reason: "Too broad — doesn't match Vikas positioning",                 source_agent: "keyword_research", source_run_id: null, cluster_id: null, created_at: "2026-04-09", position: null, prevPosition: null, url: null, contentCount: 0, trend: seededSeries(25, 12, 6100,  0.16) },
];

export const mockKeywordStats: KeywordStats = {
  total: mockKeywords.length,
  raw: mockKeywords.filter((k) => k.status === "raw").length,
  validated: mockKeywords.filter((k) => k.status === "validated").length,
  archived: mockKeywords.filter((k) => k.status === "archived").length,
  clustered: mockKeywords.filter((k) => k.status === "clustered").length,
  commercial: mockKeywords.filter((k) => k.intent === "commercial").length,
  informational: mockKeywords.filter((k) => k.intent === "informational")
    .length,
};

export const AI_SUGGESTIONS = [
  "ai email marketing automation",
  "generative ai for marketing",
  "ai social media scheduler",
  "marketing ai agents",
  "ai blog post optimizer",
];
