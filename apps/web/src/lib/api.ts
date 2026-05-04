import axios from "axios";
import { supabase } from "./supabase";
import type {
  AgentRun,
  KeywordDetail,
  KeywordRow,
  KeywordStats,
} from "./types";

const axiosInstance = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  headers: { "Content-Type": "application/json" },
});

const DEV_BYPASS = process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === "true";

axiosInstance.interceptors.request.use(async (config) => {
  if (DEV_BYPASS) return config;
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }
  return config;
});

// ── Legacy function exports (kept for backward compat) ────────────────────────

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

// Re-export types for pages that import them from here
export type { KeywordRow, KeywordStats, AgentRun, KeywordDetail };

export async function getAgentRun(runId: string): Promise<AgentRunStatus> {
  const { data } = await axiosInstance.get<AgentRunStatus>(
    `/api/v1/agents/runs/${runId}`
  );
  return data;
}

export async function getKeywords(
  status?: string,
  limit = 100
): Promise<KeywordRow[]> {
  const params: Record<string, unknown> = { limit };
  if (status) params.status = status;
  const { data } = await axiosInstance.get<KeywordRow[]>("/api/v1/keywords", {
    params,
  });
  return data;
}

export async function getKeywordStats(): Promise<KeywordStats> {
  const { data } = await axiosInstance.get<KeywordStats>(
    "/api/v1/keywords/stats"
  );
  return data;
}

export async function runKeywordResearch(
  seedKeyword: string
): Promise<AgentRunResponse> {
  const { data } = await axiosInstance.post<AgentRunResponse>(
    "/api/v1/keywords/research",
    { seed_keyword: seedKeyword }
  );
  return data;
}

// ── Namespaced api object (used by Keywords page) ─────────────────────────────

export const api = {
  keywords: {
    list: (params?: { status?: string; intent?: string; limit?: number }) => {
      const p: Record<string, string> = {};
      if (params?.status) p.status = params.status;
      if (params?.intent) p.intent = params.intent;
      if (params?.limit) p.limit = String(params.limit);
      return axiosInstance
        .get<KeywordRow[]>("/api/v1/keywords", { params: p })
        .then((r) => r.data);
    },

    stats: () =>
      axiosInstance
        .get<KeywordStats>("/api/v1/keywords/stats")
        .then((r) => r.data),

    research: (seed_keyword: string) =>
      axiosInstance
        .post<{ run_id: string }>("/api/v1/keywords/research", {
          seed_keyword,
        })
        .then((r) => r.data),

    validateAll: () =>
      axiosInstance
        .post<{ run_id: string | null; keyword_count: number }>(
          "/api/v1/keywords/validate-all"
        )
        .then((r) => r.data),

    validate: (keyword_ids: string[]) =>
      axiosInstance
        .post<{ run_id: string }>("/api/v1/keywords/validate", {
          keyword_ids,
        })
        .then((r) => r.data),

    detail: (id: string) =>
      axiosInstance
        .get<KeywordDetail>(`/api/v1/keywords/${id}/detail`)
        .then((r) => r.data),
  },

  runs: {
    get: (run_id: string) =>
      axiosInstance
        .get<AgentRun>(`/api/v1/agents/runs/${run_id}`)
        .then((r) => r.data),
  },
};

export default axiosInstance;
