'use client'

import { useState, useMemo } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Opportunity } from '@/lib/types'

const PAGE_SIZE = 20

// ── Composite score bar (Change 1 + 2) ───────────────────────────────────────
// Scores are stored on a 0-10 scale (max ~15 with intent multiplier, but practical max ~10).
// Bar is normalised against 10 so a perfect-base score fills the bar.

function compositeConfig(score: number) {
  if (score >= 8) return { label: 'Excellent', textColor: 'text-green-700', barColor: 'bg-green-500' }
  if (score >= 6) return { label: 'Good',      textColor: 'text-blue-700',  barColor: 'bg-blue-500'  }
  if (score >= 4) return { label: 'Fair',      textColor: 'text-amber-700', barColor: 'bg-amber-400' }
  return               { label: 'Weak',      textColor: 'text-gray-400',  barColor: 'bg-gray-300'  }
}

function CompositeScoreBar({ value }: { value: number | null }) {
  if (value == null) return <span className="text-xs text-gray-400">—</span>
  const pct = Math.min(value / 10, 1) * 100
  const { label, textColor, barColor } = compositeConfig(value)
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 rounded-full bg-gray-100 overflow-hidden flex-shrink-0">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular-nums text-xs font-semibold text-gray-800">
        {Math.min(value, 10).toFixed(2)}
      </span>
      <span className={`text-xs font-medium ${textColor}`}>{label}</span>
    </div>
  )
}

// ── Sub-score badge (Change 3) ────────────────────────────────────────────────
// Sub-scores (search, gap, trend, engage) are each 0-10.
// Gap and trend use 5.0 as placeholder when their agents haven't run.

type ScoreLevel = 'high' | 'medium' | 'low' | 'pending'

const LEVEL: Record<ScoreLevel, { label: string; bar: string; text: string; bg: string; border: string }> = {
  high:    { label: 'High',    bar: 'bg-green-500',  text: 'text-green-700',  bg: 'bg-green-50',  border: 'border-green-200'              },
  medium:  { label: 'Medium',  bar: 'bg-amber-400',  text: 'text-amber-700',  bg: 'bg-amber-50',  border: 'border-amber-200'              },
  low:     { label: 'Low',     bar: 'bg-orange-400', text: 'text-orange-700', bg: 'bg-orange-50', border: 'border-orange-200'             },
  pending: { label: 'Pending', bar: 'bg-gray-200',   text: 'text-gray-400',   bg: 'bg-gray-50',   border: 'border-dashed border-gray-300' },
}

function scoreLevel(value: number, isPendingCapable: boolean): ScoreLevel {
  if (isPendingCapable && Math.abs(value - 5.0) < 0.01) return 'pending'
  if (value > 7.0) return 'high'
  if (value >= 4.0) return 'medium'
  return 'low'
}

function SubScoreBadge({
  icon, label, value, tooltip, isPendingCapable = false,
}: {
  icon: string
  label: string
  value: number | null
  tooltip: string
  isPendingCapable?: boolean
}) {
  if (value == null) return null
  const level = scoreLevel(value, isPendingCapable)
  const cfg = LEVEL[level]
  const pct = level === 'pending' ? 0 : Math.min(value / 10, 1) * 100
  return (
    <div
      title={tooltip}
      className={`flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs cursor-help ${cfg.bg} ${cfg.border}`}
    >
      <span>{icon}</span>
      <span className="text-gray-600 font-medium">{label}</span>
      <div className="h-1 w-8 rounded-full bg-gray-200 overflow-hidden">
        <div className={`h-full rounded-full ${cfg.bar}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`font-medium ${cfg.text}`}>{cfg.label}</span>
    </div>
  )
}

// ── Status badge (Change 5) ───────────────────────────────────────────────────

const STATUS_CFG: Record<string, { label: string; bg: string; text: string }> = {
  new:         { label: 'Ready to write', bg: 'bg-blue-50',  text: 'text-blue-700'  },
  in_progress: { label: 'Writing…',       bg: 'bg-amber-50', text: 'text-amber-700' },
  done:        { label: 'Published',      bg: 'bg-green-50', text: 'text-green-700' },
  skipped:     { label: 'Skipped',        bg: 'bg-gray-100', text: 'text-gray-500'  },
}

function StatusBadge({ status }: { status: string }) {
  const cfg = STATUS_CFG[status] ?? { label: status, bg: 'bg-gray-100', text: 'text-gray-500' }
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cfg.bg} ${cfg.text}`}>
      {cfg.label}
    </span>
  )
}

// ── Stat card (Change 8) ──────────────────────────────────────────────────────

function StatCard({ label, value, sub }: { label: string; value: number; sub: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
      <p className="text-2xl font-bold text-gray-900 tabular-nums">{value}</p>
      <p className="text-sm font-medium text-gray-700 mt-0.5">{label}</p>
      <p className="text-xs text-gray-400">{sub}</p>
    </div>
  )
}

// ── Shared icons ──────────────────────────────────────────────────────────────

function XIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
    </svg>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

const FILTER_TABS = [
  { key: 'all',       label: 'All'       },
  { key: 'ready',     label: 'Ready'     },
  { key: 'writing',   label: 'Writing'   },
  { key: 'published', label: 'Published' },
  { key: 'skipped',   label: 'Skipped'   },
]

const FILTER_TO_STATUS: Record<string, string> = {
  ready: 'new', writing: 'in_progress', published: 'done', skipped: 'skipped',
}

export default function OpportunitiesPage() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter]     = useState('all')
  const [currentPage, setCurrentPage]       = useState(1)
  const [bannerDismissed, setBannerDismissed] = useState(false)
  const [triggerRunId, setTriggerRunId]     = useState<string | null>(null)
  const [triggerOppId, setTriggerOppId]     = useState<string | null>(null)
  const [triggerError, setTriggerError]     = useState<string | null>(null)
  const [successMsg, setSuccessMsg]         = useState<string | null>(null)

  // Change 1: always sort by composite_score desc, fetch generously for client pagination
  const { data: allOpportunities = [], isLoading } = useQuery({
    queryKey: ['opportunities'],
    queryFn: () => api.opportunities.list({ order: 'composite_score_desc', limit: 200 }),
    retry: false,
  })

  // Poll in-flight run
  const { data: liveRun } = useQuery({
    queryKey: ['run', triggerRunId],
    queryFn: () => api.runs.get(triggerRunId!),
    enabled: !!triggerRunId,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 1500 : false),
  })

  if ((liveRun?.status === 'success' || liveRun?.status === 'partial') && triggerRunId) {
    setTriggerRunId(null)
    setTriggerOppId(null)
    setSuccessMsg('Content pipeline started — check the dashboard for progress.')
    queryClient.invalidateQueries({ queryKey: ['opportunities'] })
    setTimeout(() => setSuccessMsg(null), 5000)
  }

  // Change 8: stat counts
  const stats = useMemo(() => ({
    total:     allOpportunities.length,
    ready:     allOpportunities.filter((o) => o.status === 'new').length,
    writing:   allOpportunities.filter((o) => o.status === 'in_progress').length,
    published: allOpportunities.filter((o) => o.status === 'done').length,
  }), [allOpportunities])

  // Change 6: gap=5.0 and trend=5.0 are hardcoded placeholders in opportunity_scorer
  const hasPendingScores = useMemo(() =>
    allOpportunities.some((o) =>
      (o.competitive_gap_score != null && Math.abs(o.competitive_gap_score - 5.0) < 0.01) ||
      (o.trend_score != null && Math.abs(o.trend_score - 5.0) < 0.01)
    ),
    [allOpportunities]
  )

  // Change 5 + 7: filter + client-side pagination
  const filtered = useMemo(() => {
    if (statusFilter === 'all') return allOpportunities
    const apiStatus = FILTER_TO_STATUS[statusFilter] ?? statusFilter
    return allOpportunities.filter((o) => o.status === apiStatus)
  }, [allOpportunities, statusFilter])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const page = Math.min(currentPage, totalPages)
  const pageItems = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  function setFilter(f: string) {
    setStatusFilter(f)
    setCurrentPage(1)
  }

  async function handleCreateContent(opp: Opportunity) {
    setTriggerError(null)
    setTriggerOppId(opp.id)
    try {
      const { run_id } = await api.agents.run('content_director', { opportunity_id: opp.id })
      setTriggerRunId(run_id)
    } catch {
      setTriggerError(`Failed to start pipeline for "${opp.keyword}"`)
      setTriggerOppId(null)
    }
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-gray-900">Opportunities</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Keyword opportunities ranked by composite score
        </p>
      </div>

      {/* Change 8 — stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard label="Total"     value={stats.total}     sub="found"       />
        <StatCard label="Ready"     value={stats.ready}     sub="to write"    />
        <StatCard label="Writing"   value={stats.writing}   sub="in progress" />
        <StatCard label="Published" value={stats.published} sub="live"        />
      </div>

      {/* Change 6 — data confidence banner */}
      {hasPendingScores && !bannerDismissed && (
        <div className="flex items-start justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <div className="flex gap-2.5">
            <span className="text-base leading-none mt-0.5" aria-hidden>⚠️</span>
            <div>
              <p className="font-medium">Some scores are pending real data.</p>
              <p className="text-xs text-amber-700 mt-0.5">
                Run{' '}
                <code className="font-mono bg-amber-100 px-1 rounded">gap_analyzer</code> and{' '}
                <code className="font-mono bg-amber-100 px-1 rounded">trend_collector</code>{' '}
                to get accurate opportunity scores.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setBannerDismissed(true)}
            className="text-amber-400 hover:text-amber-600 flex-shrink-0 mt-0.5"
          >
            <XIcon />
          </button>
        </div>
      )}

      {/* Success / error banners */}
      {successMsg && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-700">
          <span>{successMsg}</span>
          <button type="button" onClick={() => setSuccessMsg(null)} className="text-green-400 hover:text-green-600">
            <XIcon />
          </button>
        </div>
      )}
      {triggerError && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          <span>{triggerError}</span>
          <button type="button" onClick={() => setTriggerError(null)} className="text-red-400 hover:text-red-600">
            <XIcon />
          </button>
        </div>
      )}

      {/* Change 5 — filter tabs with human-readable labels */}
      <div className="flex flex-wrap gap-1.5">
        {FILTER_TABS.map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setFilter(key)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              statusFilter === key
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Change 4 + 7 — card list with pagination */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-lg bg-gray-100" />
          ))}
        </div>
      ) : pageItems.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-sm text-gray-400">
            No opportunities{statusFilter !== 'all' ? ` matching this filter` : ''}.{' '}
            <span className="text-gray-500">
              Run keyword research + gap analysis to generate opportunities.
            </span>
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {pageItems.map((opp) => {
            const isTriggering = triggerOppId === opp.id
            const gapTooltip = opp.competitive_gap_score != null && Math.abs(opp.competitive_gap_score - 5.0) < 0.01
              ? 'Gap score: Pending — run gap_analyzer'
              : 'Gap score: Competitive gap opportunity'
            const trendTooltip = opp.trend_score != null && Math.abs(opp.trend_score - 5.0) < 0.01
              ? 'Trend score: Pending — run trend_collector'
              : 'Trend score: Based on search trend momentum'

            return (
              <div
                key={opp.id}
                className="rounded-lg border border-gray-200 bg-white px-4 py-3.5 hover:border-indigo-200 hover:shadow-sm transition-all"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    {/* Change 4 row 1 — keyword name + status badge */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-gray-900 text-sm leading-snug">
                        {opp.keyword}
                      </span>
                      <StatusBadge status={opp.status} />
                    </div>

                    {/* Source (secondary) */}
                    <p className="text-xs text-gray-400 mt-0.5 font-mono">{opp.source}</p>

                    {/* Change 2 — composite score bar with colour coding */}
                    <div className="mt-2.5">
                      <CompositeScoreBar value={opp.composite_score} />
                    </div>

                    {/* Change 3 — sub-score icon badges */}
                    <div className="flex flex-wrap gap-1.5 mt-2">
                      <SubScoreBadge
                        icon="🔍" label="Search" value={opp.search_score}
                        tooltip="Search score: Based on monthly search volume"
                      />
                      <SubScoreBadge
                        icon="📊" label="Gap" value={opp.competitive_gap_score}
                        tooltip={gapTooltip}
                        isPendingCapable
                      />
                      <SubScoreBadge
                        icon="📈" label="Trend" value={opp.trend_score}
                        tooltip={trendTooltip}
                        isPendingCapable
                      />
                      <SubScoreBadge
                        icon="💬" label="Engage" value={opp.engagement_score}
                        tooltip="Engage score: Based on commercial intent signals"
                      />
                    </div>
                  </div>

                  {/* Change 4 — Write CTA always visible for ready opportunities */}
                  {opp.status === 'new' && (
                    <div className="flex-shrink-0 pt-1">
                      <button
                        type="button"
                        disabled={!!triggerOppId}
                        onClick={() => handleCreateContent(opp)}
                        className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {isTriggering ? (
                          <><Spinner /> Running…</>
                        ) : (
                          <>Write <span aria-hidden>→</span></>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Change 7 — pagination */}
      {!isLoading && filtered.length > PAGE_SIZE && (
        <div className="flex items-center justify-between border-t border-gray-100 pt-4">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setCurrentPage((p) => p - 1)}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            ← Previous
          </button>
          <span className="text-xs text-gray-500">
            Page {page} of {totalPages} ({filtered.length}{' '}
            {filtered.length === 1 ? 'opportunity' : 'opportunities'})
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => setCurrentPage((p) => p + 1)}
            className="rounded-md border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next →
          </button>
        </div>
      )}
    </div>
  )
}
