'use client'

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Badge, statusBadgeVariant } from '@/components/ui/badge'
import type { StrategyRecommendation } from '@/lib/types'

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

const IMPACT_COLORS: Record<string, string> = {
  high: 'bg-green-100 text-green-700',
  medium: 'bg-amber-100 text-amber-700',
  low: 'bg-gray-100 text-gray-600',
}

function ImpactBadge({ impact }: { impact: string | undefined }) {
  if (!impact) return null
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${IMPACT_COLORS[impact] ?? 'bg-gray-100 text-gray-600'}`}
    >
      {impact} impact
    </span>
  )
}

function PriorityDot({ priority }: { priority: number }) {
  const color = priority <= 2 ? 'bg-red-500' : priority <= 5 ? 'bg-amber-400' : 'bg-gray-300'
  return (
    <span
      className={`inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white ${color}`}
    >
      {priority}
    </span>
  )
}

function RecommendationCard({ rec }: { rec: StrategyRecommendation }) {
  return (
    <div className="flex gap-4 rounded-lg border border-gray-200 bg-white px-5 py-4 hover:border-gray-300 transition-colors">
      <PriorityDot priority={rec.priority} />
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-3">
          <p className="text-sm font-medium text-gray-900 leading-snug">{rec.action}</p>
          <ImpactBadge impact={rec.expected_impact} />
        </div>
        {rec.rationale && (
          <p className="mt-1.5 text-xs text-gray-500 leading-relaxed">{rec.rationale}</p>
        )}
      </div>
    </div>
  )
}

export default function StrategyPage() {
  const queryClient = useQueryClient()
  const [triggerRunId, setTriggerRunId] = useState<string | null>(null)
  const [triggerError, setTriggerError] = useState<string | null>(null)

  const { data: report, isLoading, isError } = useQuery({
    queryKey: ['strategy-report'],
    queryFn: api.strategy.latestReport,
    retry: false,
  })

  // Poll in-flight synthesis run
  const { data: liveRun } = useQuery({
    queryKey: ['run', triggerRunId],
    queryFn: () => api.runs.get(triggerRunId!),
    enabled: !!triggerRunId,
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 2000 : false,
  })

  if (
    (liveRun?.status === 'success' || liveRun?.status === 'partial') &&
    triggerRunId
  ) {
    setTriggerRunId(null)
    queryClient.invalidateQueries({ queryKey: ['strategy-report'] })
  }

  async function handleRunSynthesis() {
    setTriggerError(null)
    try {
      const { run_id } = await api.agents.run('strategy_synthesizer', { limit: 10 })
      setTriggerRunId(run_id)
    } catch {
      setTriggerError('Failed to trigger strategy synthesis — is the API running?')
    }
  }

  const recommendations: StrategyRecommendation[] = Array.isArray(report?.recommendations)
    ? report.recommendations
    : []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-gray-900">Strategy</h1>
          {report ? (
            <p className="text-sm text-gray-400 mt-0.5">
              Report generated {timeAgo(report.created_at)} · {report.opportunities_analyzed} opportunities analyzed
            </p>
          ) : (
            <p className="text-sm text-gray-400 mt-0.5">
              Run the strategy synthesizer to generate recommendations
            </p>
          )}
        </div>
        <button
          type="button"
          disabled={!!triggerRunId}
          onClick={handleRunSynthesis}
          className="shrink-0 inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {triggerRunId ? (
            <>
              <svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
              </svg>
              Synthesizing…
            </>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              Run Synthesis
            </>
          )}
        </button>
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

      {isLoading ? (
        <div className="space-y-4">
          <div className="h-24 animate-pulse rounded-lg bg-gray-100" />
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-16 animate-pulse rounded-lg bg-gray-100" />
            ))}
          </div>
        </div>
      ) : isError || !report ? (
        <div className="py-20 text-center">
          <svg
            className="mx-auto mb-3 text-gray-300"
            width="40"
            height="40"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="18" y1="20" x2="18" y2="10" />
            <line x1="12" y1="20" x2="12" y2="4" />
            <line x1="6" y1="20" x2="6" y2="14" />
          </svg>
          <p className="text-sm font-medium text-gray-500">No strategy report yet</p>
          <p className="text-xs text-gray-400 mt-1">
            Click "Run Synthesis" to generate your first report
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Summary card */}
          {report.summary && (
            <div className="rounded-lg border border-indigo-100 bg-indigo-50 px-5 py-4">
              <div className="flex items-start justify-between gap-3 mb-2">
                <p className="text-xs font-semibold text-indigo-600 uppercase tracking-wide">
                  Executive Summary
                </p>
                <Badge variant={statusBadgeVariant(report.status)}>{report.status}</Badge>
              </div>
              <p className="text-sm text-gray-700 leading-relaxed">{report.summary}</p>
            </div>
          )}

          {/* Stats row */}
          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-center">
              <p className="text-2xl font-semibold tabular-nums text-gray-900">
                {report.opportunities_analyzed}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">Opportunities analyzed</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-center">
              <p className="text-2xl font-semibold tabular-nums text-gray-900">
                {recommendations.length}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">Recommendations</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-center">
              <p className="text-2xl font-semibold tabular-nums text-gray-900">
                {recommendations.filter((r) => r.expected_impact === 'high').length}
              </p>
              <p className="text-xs text-gray-400 mt-0.5">High-impact actions</p>
            </div>
          </div>

          {/* Recommendations */}
          {recommendations.length > 0 ? (
            <div>
              <h2 className="text-sm font-semibold text-gray-700 mb-3">
                Recommendations — by priority
              </h2>
              <div className="space-y-2.5">
                {[...recommendations]
                  .sort((a, b) => a.priority - b.priority)
                  .map((rec, i) => (
                    <RecommendationCard key={i} rec={rec} />
                  ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-400 text-center py-6">
              No recommendations in this report.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
