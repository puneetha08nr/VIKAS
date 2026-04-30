export type AgentStatus = "pending" | "running" | "success" | "failed" | "partial";

export type ContentStatus = "draft" | "review" | "approved" | "published";

export type LLMTier = "fast" | "standard" | "advanced";

export interface AgentRun {
  id: string;
  orgId: string;
  agentName: string;
  status: AgentStatus;
  durationMs: number;
  tokensIn: number;
  tokensOut: number;
  costUsd: number;
  modelUsed: string;
  error?: string;
  startedAt: string;
}

export interface Keyword {
  id: string;
  orgId: string;
  keyword: string;
  volume: number;
  kd: number;
  cpc: number;
  clusterId?: string;
  status: string;
  sourceAgent: string;
  createdAt: string;
  updatedAt: string;
}

export interface ContentItem {
  id: string;
  orgId: string;
  opportunityId: string;
  format: string;
  title: string;
  body: string;
  status: ContentStatus;
  brandVoiceScore?: number;
  seoScore?: number;
  publishedUrl?: string;
  createdAt: string;
  updatedAt: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  settings: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}
