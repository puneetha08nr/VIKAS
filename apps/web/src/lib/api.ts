import axios from "axios";
import { supabase } from "./supabase";

const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

api.interceptors.request.use(async (config) => {
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }
  return config;
});

// ── Typed API calls ───────────────────────────────────────────────────────────

export interface AgentRunResponse {
  run_id: string;
}

export interface AgentRunStatus {
  run_id: string;
  agent_name: string;
  status: "running" | "success" | "failed" | "partial";
  duration_ms: number | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  model_used: string | null;
  error: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface KeywordRow {
  id: string;
  keyword: string;
  volume: number | null;
  kd: number | null;
  cpc: number | null;
  intent: string | null;
  reason: string | null;
  status: "raw" | "validated" | "clustered" | "archived";
  source_agent: string;
  created_at: string;
}

export interface KeywordStats {
  total: number;
  raw: number;
  validated: number;
  archived: number;
  commercial: number;
  informational: number;
}

export async function triggerAgent(
  agentName: string,
  params: Record<string, unknown>
): Promise<AgentRunResponse> {
  const { data } = await api.post<AgentRunResponse>("/api/v1/agents/run", {
    agent_name: agentName,
    params,
  });
  return data;
}

export async function getAgentRun(runId: string): Promise<AgentRunStatus> {
  const { data } = await api.get<AgentRunStatus>(`/api/v1/agents/runs/${runId}`);
  return data;
}

export async function getKeywords(
  status?: string,
  limit = 100
): Promise<KeywordRow[]> {
  const params: Record<string, unknown> = { limit };
  if (status) params.status = status;
  const { data } = await api.get<KeywordRow[]>("/api/v1/keywords", { params });
  return data;
}

export async function getKeywordStats(): Promise<KeywordStats> {
  const { data } = await api.get<KeywordStats>("/api/v1/keywords/stats");
  return data;
}

export async function runKeywordResearch(
  seedKeyword: string
): Promise<AgentRunResponse> {
  const { data } = await api.post<AgentRunResponse>("/api/v1/keywords/research", {
    seed_keyword: seedKeyword,
  });
  return data;
}

export default api;
