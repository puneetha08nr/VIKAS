'use client'

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Badge, statusBadgeVariant } from '@/components/ui/badge'
import type { Opportunity } from '@/lib/types'

function ScoreBar({ value }: { value: number | null }) {
  const pct = value != null ? Math.min(Math.max(value * 100, 0), 100) : 0
  const color =
    pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 rounded-full bg-gray-100 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular-nums text-xs text-gray-600">
        {value != null ? value.toFixed(2) : '—'}
      </span>
    </div>
  )
}

function SubScore({
  label,
  value,
}: {
  label: string
  value: number | null
}) {
  if (value == null) return null
  const pct = Math.min(Math.max(value * 100, 0), 100)
  const color =
    pct >= 70 ? 'text-green-600' : pct >= 40 ? 'text-amber-600' : 'text-red-500'
  return (
    <span className={`text-xs font-medium ${color}`}>
      {label} {pct.toFixed(0)}
    </span>
  )
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    open: 'Open',
    in_progress: 'In Progress',
    done: 'Done',
    skipped: 'Skipped',
  }
  return labels[status] ?? status
}

export default function OpportunitiesPage() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [triggerRunId, setTriggerRunId] = useState<string | null>(null)
  const [triggerOppId, setTriggerOppId] = useState<string | null>(null)
  const [triggerError, setTriggerError] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)

  const { data: opportunities = [], isLoading } = useQuery({
    queryKey: ['opportunities', statusFilter],
    queryFn: () =>
      api.opportunities.list({
        status: statusFilter === 'all' ? undefined : statusFilter,
        order: 'desc',
        limit: 100,
      }),
    retry: false,
  })

  // Poll in-flight run
  const { data: liveRun } = useQuery({
    queryKey: ['run', triggerRunId],
    queryFn: () => api.runs.get(triggerRunId!),
    enabled: !!triggerRunId,
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 1500 : false,
  })

  if (
    (liveRun?.status === 'success' || liveRun?.status === 'partial') &&
    triggerRunId
  ) {
    setTriggerRunId(null)
    setTriggerOppId(null)
    setSuccessMsg('Content pipeline started — check the dashboard for progress.')
    queryClient.invalidateQueries({ queryKey: ['opportunities'] })
    setTimeout(() => setSuccessMsg(null), 5000)
  }

  async function handleCreateContent(opp: Opportunity) {
    setTriggerError(null)
    setTriggerOppId(opp.id)
    try {
      const { run_id } = await api.agents.run('content_director', {
        opportunity_id: opp.id,
      })
      setTriggerRunId(run_id)
    } catch {
      setTriggerError(`Failed to start pipeline for "${opp.keyword}"`)
      setTriggerOppId(null)
    }
  }

  const STATUS_FILTERS = ['all', 'open', 'in_progress', 'done', 'skipped']

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-gray-900">
            Opportunities
          </h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {opportunities.length} opportunity{opportunities.length !== 1 ? 'ies' : 'y'} found
          </p>
        </div>
      </div>

      {/* Success / error banners */}
      {successMsg && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-700">
          <span>{successMsg}</span>
          <button type="button" onClick={() => setSuccessMsg(null)} className="text-green-400 hover:text-green-600">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        </div>
      )}
      {triggerError && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          <span>{triggerError}</span>
          <button type="button" onClick={() => setTriggerError(null)} className="text-red-400 hover:text-red-600">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
        </div>
      )}

      {/* Filter pills */}
      <div className="flex flex-wrap gap-1.5">
        {STATUS_FILTERS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatusFilter(s)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              statusFilter === s
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {s === 'all' ? 'All' : statusLabel(s)}
          </button>
        ))}
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="space-y-2">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded bg-gray-100" />
          ))}
        </div>
      ) : opportunities.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-sm text-gray-400">
            No opportunities yet.{' '}
            <span className="text-gray-500">
              Run keyword research + gap analysis to generate opportunities.
            </span>
          </p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full divide-y divide-gray-100 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">
                  Keyword
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">
                  Composite Score
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden md:table-cell">
                  Sub-scores
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden sm:table-cell">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden lg:table-cell">
                  Source
                </th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {opportunities.map((opp) => {
                const isTriggering = triggerOppId === opp.id
                return (
                  <tr key={opp.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <span className="font-medium text-gray-900">
                        {opp.keyword}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <ScoreBar value={opp.composite_score} />
                    </td>
                    <td className="px-4 py-3 hidden md:table-cell">
                      <div className="flex flex-wrap gap-2">
                        <SubScore label="Search" value={opp.search_score} />
                        <SubScore label="Gap" value={opp.competitive_gap_score} />
                        <SubScore label="Trend" value={opp.trend_score} />
                        <SubScore label="Engage" value={opp.engagement_score} />
                      </div>
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell">
                      <Badge variant={statusBadgeVariant(opp.status)}>
                        {statusLabel(opp.status)}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 hidden lg:table-cell">
                      <span className="font-mono text-xs text-gray-400">
                        {opp.source}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      {opp.status === 'open' && (
                        <button
                          type="button"
                          disabled={!!triggerOppId}
                          onClick={() => handleCreateContent(opp)}
                          className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {isTriggering ? (
                            <>
                              <svg
                                className="animate-spin h-3 w-3"
                                fill="none"
                                viewBox="0 0 24 24"
                              >
                                <circle
                                  className="opacity-25"
                                  cx="12"
                                  cy="12"
                                  r="10"
                                  stroke="currentColor"
                                  strokeWidth="4"
                                />
                                <path
                                  className="opacity-75"
                                  fill="currentColor"
                                  d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"
                                />
                              </svg>
                              Running…
                            </>
                          ) : (
                            'Create content'
                          )}
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
