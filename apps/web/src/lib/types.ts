export type KeywordStatus = 'raw' | 'validated' | 'clustered' | 'archived'
export type KeywordIntent = 'commercial' | 'informational' | 'transactional' | 'navigational'
export type DataSource = 'dataforseo' | 'llm_estimate'
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
