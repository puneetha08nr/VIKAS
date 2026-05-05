'use client'

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '@/lib/api'
import { Badge, statusBadgeVariant } from '@/components/ui/badge'
import type { AgentRun, Opportunity } from '@/lib/types'

function MetricCard({
  label,
  value,
  subtitle,
  loading,
}: {
  label: string
  value: string | number
  subtitle?: string
  loading?: boolean
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-5 py-4">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{label}</p>
      {loading ? (
        <div className="mt-2 h-7 w-16 animate-pulse rounded bg-gray-100" />
      ) : (
        <p className="mt-1 text-2xl font-semibold tabular-nums text-gray-900">{value}</p>
      )}
      {subtitle && <p className="mt-0.5 text-xs text-gray-400">{subtitle}</p>}
    </div>
  )
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function RunStatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    success: 'bg-green-500',
    failed: 'bg-red-500',
    running: 'bg-amber-400 animate-pulse',
    partial: 'bg-blue-400',
  }
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full shrink-0 ${colors[status] ?? 'bg-gray-300'}`}
    />
  )
}

export default function DashboardPage() {
  const queryClient = useQueryClient()
  const [triggerError, setTriggerError] = useState<string | null>(null)
  const [triggerRunId, setTriggerRunId] = useState<string | null>(null)

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['keyword-stats'],
    queryFn: api.keywords.stats,
  })

  const { data: runs = [], isLoading: runsLoading } = useQuery({
    queryKey: ['agent-runs', 10],
    queryFn: () => api.runs.list(10),
  })

  const { data: opportunities = [] } = useQuery({
    queryKey: ['opportunities', 1],
    queryFn: () => api.opportunities.list({ limit: 5 }),
    retry: false,
  })

  const { data: draftArticles = [] } = useQuery({
    queryKey: ['articles', 'draft'],
    queryFn: () => api.articles.list({ status: 'draft', limit: 1 }),
    retry: false,
  })

  // Poll in-flight run until it settles
  const { data: liveRun } = useQuery({
    queryKey: ['run', triggerRunId],
    queryFn: () => api.runs.get(triggerRunId!),
    enabled: !!triggerRunId,
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 1500 : false,
  })

  if (liveRun?.status === 'success' || liveRun?.status === 'partial') {
    if (triggerRunId) {
      setTriggerRunId(null)
      queryClient.invalidateQueries({ queryKey: ['agent-runs'] })
    }
  }

  const topOpportunity: Opportunity | null = opportunities[0] ?? null
  const lastRun: AgentRun | null = runs[0] ?? null

  async function handleCreateContent(opportunityId: string) {
    setTriggerError(null)
    try {
      const { run_id } = await api.agents.run('content_director', { opportunity_id: opportunityId })
      setTriggerRunId(run_id)
    } catch {
      setTriggerError('Failed to trigger content pipeline — is the API running?')
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-gray-900">Dashboard</h1>
          {lastRun && (
            <p className="text-sm text-gray-400 mt-0.5">
              Last agent run: <span className="font-mono text-xs">{timeAgo(lastRun.started_at)}</span>
            </p>
          )}
        </div>
      </div>

      {/* Error banner */}
      {triggerError && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          <span>{triggerError}</span>
          <button type="button" onClick={() => setTriggerError(null)} className="text-red-400 hover:text-red-600">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Metric cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricCard
          label="Validated Keywords"
          value={stats?.validated ?? 0}
          subtitle={`${stats?.total ?? 0} total`}
          loading={statsLoading}
        />
        <MetricCard
          label="Open Opportunities"
          value={opportunities.length}
          subtitle="ready to create content"
        />
        <MetricCard
          label="Content Drafts"
          value={draftArticles.length > 0 ? draftArticles.length : (stats?.opportunities ?? 0)}
          subtitle="awaiting review"
        />
        <MetricCard
          label="Raw Keywords"
          value={stats?.raw ?? 0}
          subtitle="need validation"
          loading={statsLoading}
        />
      </div>

      {/* Top opportunity */}
      {topOpportunity && (
        <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-5 py-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-medium text-indigo-500 uppercase tracking-wide">Top Opportunity</p>
              <p className="mt-1 text-base font-semibold text-gray-900">{topOpportunity.keyword}</p>
              <p className="mt-0.5 text-xs text-gray-500">
                Composite score:{' '}
                <span className="font-semibold text-indigo-700">
                  {topOpportunity.composite_score?.toFixed(2) ?? '—'}
                </span>
              </p>
            </div>
            <button
              type="button"
              onClick={() => handleCreateContent(topOpportunity.id)}
              disabled={!!triggerRunId}
              className="shrink-0 inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {triggerRunId ? (
                <>
                  <svg className="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
                  </svg>
                  Running…
                </>
              ) : (
                'Create content'
              )}
            </button>
          </div>
        </div>
      )}

      {/* Agent runs table */}
      <div>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">Recent Agent Runs</h2>
        {runsLoading ? (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-10 animate-pulse rounded bg-gray-100" />
            ))}
          </div>
        ) : runs.length === 0 ? (
          <p className="text-sm text-gray-400 py-6 text-center">No agent runs yet. Run keyword research to get started.</p>
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-100 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">Agent</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">Status</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">Duration</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">Cost</th>
                  <th className="px-4 py-2.5 text-left text-xs font-medium text-gray-500">When</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {runs.map((run) => (
                  <tr key={run.run_id} className="hover:bg-gray-50">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <RunStatusDot status={run.status} />
                        <span className="font-mono text-xs text-gray-700">{run.agent_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5">
                      <Badge variant={statusBadgeVariant(run.status)}>{run.status}</Badge>
                    </td>
                    <td className="px-4 py-2.5 tabular-nums text-xs text-gray-500">
                      {run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)}s` : '—'}
                    </td>
                    <td className="px-4 py-2.5 tabular-nums text-xs text-gray-500">
                      {run.cost_usd != null ? `$${run.cost_usd.toFixed(4)}` : '—'}
                    </td>
                    <td className="px-4 py-2.5 text-xs text-gray-400">
                      {timeAgo(run.started_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
