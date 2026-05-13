'use client'

import { useState, useEffect, useCallback } from 'react'
import { useQuery, useQueryClient, keepPreviousData } from '@tanstack/react-query'
import { api, axiosInstance } from '@/lib/api'
import { mockKeywordStats, KW_CLUSTERS } from '@/lib/mocks'
import { KpiStrip } from './components/KpiStrip'
import { KeywordsTable } from './components/KeywordsTable'
import { KeywordDrawer } from './components/KeywordDrawer'
import { ResearchModal } from './components/ResearchModal'
import type { KeywordRow } from '@/lib/types'

const LIMIT = 20

const SORT_OPTIONS = [
  { value: 'created_at:desc', label: 'Newest first' },
  { value: 'created_at:asc',  label: 'Oldest first' },
  { value: 'volume:desc',     label: 'Volume H→L' },
  { value: 'volume:asc',      label: 'Volume L→H' },
  { value: 'kd:asc',          label: 'KD L→H' },
  { value: 'kd:desc',         label: 'KD H→L' },
  { value: 'cpc:desc',        label: 'CPC H→L' },
] as const

const STATUS_OPTS = ['all', 'raw', 'validated', 'clustered', 'archived'] as const
const INTENT_OPTS = ['all', 'commercial', 'informational', 'transactional', 'navigational'] as const
const SOURCE_OPTS = ['all', 'dataforseo', 'pending'] as const

export default function KeywordsPage() {
  const queryClient = useQueryClient()

  // ── Filter / sort / pagination state ────────────────────────────────────────
  const [statusFilter, setStatusFilter] = useState('all')
  const [intentFilter, setIntentFilter] = useState('all')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [sortKey, setSortKey] = useState('created_at:desc')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')

  useEffect(() => {
    const t = setTimeout(() => { setDebouncedSearch(search); setPage(1) }, 350)
    return () => clearTimeout(t)
  }, [search])

  const [sortCol, sortOrder] = sortKey.split(':') as [string, string]
  const offset = (page - 1) * LIMIT

  // ── Selection state ──────────────────────────────────────────────────────────
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // ── Drawer / modal state ─────────────────────────────────────────────────────
  const [openKeyword, setOpenKeyword] = useState<KeywordRow | null>(null)
  const [researchOpen, setResearchOpen] = useState(false)

  // ── Run tracking ─────────────────────────────────────────────────────────────
  const [researchRunId, setResearchRunId] = useState<string | null>(null)
  const [validateRunId, setValidateRunId] = useState<string | null>(null)
  const [validatingCount, setValidatingCount] = useState(0)
  const [validatingRowId, setValidatingRowId] = useState<string | null>(null)
  const [validatingKeyword, setValidatingKeyword] = useState<string | null>(null)

  // ── UI state ─────────────────────────────────────────────────────────────────
  const [isResearching, setIsResearching] = useState(false)
  const [researchError, setResearchError] = useState<string | null>(null)
  const [apiError, setApiError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [isFetchingMetrics, setIsFetchingMetrics] = useState(false)
  const [contentRunId, setContentRunId] = useState<string | null>(null)
  const [contentLoadingKwId, setContentLoadingKwId] = useState<string | null>(null)

  // ── Queries ──────────────────────────────────────────────────────────────────

  const kwQueryKey = ['keywords', { statusFilter, intentFilter, sourceFilter, sortCol, sortOrder, page, debouncedSearch }]

  const { data: kwPage, isLoading: kwLoading } = useQuery({
    queryKey: kwQueryKey,
    queryFn: () =>
      api.keywords.list({
        status: statusFilter !== 'all' ? statusFilter : undefined,
        intent: intentFilter !== 'all' ? intentFilter : undefined,
        data_source: sourceFilter !== 'all' ? sourceFilter : undefined,
        search: debouncedSearch || undefined,
        sort: sortCol,
        order: sortOrder,
        limit: LIMIT,
        offset,
      }),
    placeholderData: keepPreviousData,
  })

  const keywords = kwPage?.keywords ?? []
  const total = kwPage?.total ?? 0
  const totalPages = kwPage?.total_pages ?? 1

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['keyword-stats'],
    queryFn: api.keywords.stats,
    initialData: mockKeywordStats,
    initialDataUpdatedAt: 0,
  })

  const { data: researchRun } = useQuery({
    queryKey: ['run', researchRunId],
    queryFn: () => api.runs.get(researchRunId!),
    enabled: !!researchRunId,
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 600 : false,
  })

  const { data: validateRun } = useQuery({
    queryKey: ['run', validateRunId],
    queryFn: () => api.runs.get(validateRunId!),
    enabled: !!validateRunId,
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 2000 : false,
  })

  const { data: contentRun } = useQuery({
    queryKey: ['run', contentRunId],
    queryFn: () => api.runs.get(contentRunId!),
    enabled: !!contentRunId,
    refetchInterval: (query) =>
      query.state.data?.status === 'running' ? 2000 : false,
  })

  const invalidateKeywords = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['keywords'] })
    queryClient.invalidateQueries({ queryKey: ['keyword-stats'] })
  }, [queryClient])

  // ── Run side effects ─────────────────────────────────────────────────────────

  useEffect(() => {
    if (!researchRun) return
    if (researchRun.status === 'success') {
      setIsResearching(false)
      setResearchRunId(null)
      setResearchError(null)
      invalidateKeywords()
      setSuccessMessage('Keywords added successfully')
    }
    if (researchRun.status === 'failed') {
      setIsResearching(false)
      setResearchRunId(null)
      setResearchError(researchRun.error ?? 'Keyword research failed. Check Settings → Integrations.')
      setResearchOpen(true)
    }
    if (researchRun.status === 'partial') {
      setIsResearching(false)
      setResearchRunId(null)
      invalidateKeywords()
      if (researchRun.error) {
        setResearchError(researchRun.error)
        setResearchOpen(true)
      } else {
        setResearchError(null)
        setSuccessMessage('Keywords added — metrics pending. Configure DataForSEO then click "Fetch metrics".')
      }
    }
  }, [researchRun?.status, invalidateKeywords])

  useEffect(() => {
    if (!validateRun) return
    if (validateRun.status === 'success') {
      setValidateRunId(null)
      setValidatingCount(0)
      setValidatingRowId(null)
      setValidatingKeyword(null)
      invalidateKeywords()
      setSuccessMessage('Validation complete — keywords updated')
    }
    if (validateRun.status === 'failed') {
      setValidateRunId(null)
      setValidatingCount(0)
      setValidatingRowId(null)
      setValidatingKeyword(null)
      setApiError(validateRun.error ?? 'Validation failed')
    }
  }, [validateRun?.status, invalidateKeywords])

  useEffect(() => {
    if (!contentRun) return
    if (contentRun.status === 'success') {
      setContentRunId(null)
      setContentLoadingKwId(null)
      setSuccessMessage('Content pipeline started — check Content page in ~15 min')
    }
    if (contentRun.status === 'failed') {
      setContentRunId(null)
      setContentLoadingKwId(null)
      setApiError(contentRun.error ?? 'Content pipeline failed')
    }
  }, [contentRun?.status])

  // ── Selection helpers ────────────────────────────────────────────────────────

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (keywords.every((r) => selectedIds.has(r.id))) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(keywords.map((r) => r.id)))
    }
  }

  // ── Action handlers ──────────────────────────────────────────────────────────

  const handleResearch = async (seed: string) => {
    setApiError(null)
    setResearchError(null)
    try {
      const { run_id } = await api.keywords.research(seed)
      setResearchRunId(run_id)
      setIsResearching(true)
      setResearchOpen(false)
    } catch (err) {
      setResearchError(err instanceof Error ? err.message : 'Research failed — is the API running?')
    }
  }

  const handleValidateAll = async () => {
    if (!stats?.raw || validateRunId) return
    setApiError(null)
    setSuccessMessage(null)
    try {
      const result = await api.keywords.validateAll()
      if (!result.run_id) {
        setSuccessMessage('No raw keywords to validate')
        return
      }
      setValidateRunId(result.run_id)
      setValidatingCount(result.keyword_count)
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Validation failed — is the API running?')
    }
  }

  const handleValidateSelected = async () => {
    if (selectedIds.size === 0 || validateRunId) return
    setApiError(null)
    try {
      const { run_id } = await api.keywords.validate([...selectedIds])
      setValidateRunId(run_id)
      setSelectedIds(new Set())
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Validation failed — is the API running?')
    }
  }

  const handleValidateRow = async (keyword_id: string) => {
    setApiError(null)
    setSuccessMessage(null)
    setValidatingRowId(keyword_id)
    const kw = keywords.find((k) => k.id === keyword_id)
    setValidatingKeyword(kw?.keyword ?? null)
    try {
      const { run_id } = await api.keywords.validate([keyword_id])
      setValidateRunId(run_id)
      setValidatingCount(1)
    } catch (err) {
      setValidatingRowId(null)
      setValidatingKeyword(null)
      setApiError(err instanceof Error ? err.message : 'Validation failed')
    }
  }

  const handleCreateContent = async (keyword: KeywordRow) => {
    setApiError(null)
    setSuccessMessage(null)
    setContentLoadingKwId(keyword.id)
    try {
      const opportunities = await api.opportunities.list({ limit: 200 })
      const opp = opportunities.find((o: any) => o.keyword_id === keyword.id)
      if (!opp) {
        setContentLoadingKwId(null)
        setApiError(`No opportunity found for "${keyword.keyword}" — run opportunity scorer first`)
        return
      }
      const res = await axiosInstance.post('/api/v1/agents/content_director/run', {
        params: { opportunity_id: opp.id },
      })
      setContentRunId(res.data.run_id)
    } catch (err) {
      setContentLoadingKwId(null)
      setApiError(err instanceof Error ? err.message : 'Failed to start content pipeline')
    }
  }

  const handleFetchMetrics = async () => {
    setIsFetchingMetrics(true)
    setApiError(null)
    setSuccessMessage(null)
    try {
      const result = await api.keywords.fetchMetrics()
      invalidateKeywords()
      setSuccessMessage(
        result.updated > 0
          ? `Metrics fetched — ${result.updated} keyword${result.updated === 1 ? '' : 's'} updated`
          : 'No pending keywords to update'
      )
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Failed to fetch metrics — is DataForSEO configured?')
    } finally {
      setIsFetchingMetrics(false)
    }
  }

  const clearFilters = () => {
    setStatusFilter('all')
    setIntentFilter('all')
    setSourceFilter('all')
    setSearch('')
    setDebouncedSearch('')
    setPage(1)
  }

  // ── Derived values ───────────────────────────────────────────────────────────

  const isValidating = validateRun?.status === 'running' || !!validateRunId
  const rawCount = stats?.raw ?? 0
  const pendingCount = stats?.pending ?? 0
  const hasFilters = statusFilter !== 'all' || intentFilter !== 'all' || sourceFilter !== 'all' || debouncedSearch !== ''

  const pageFrom = total === 0 ? 0 : offset + 1
  const pageTo = Math.min(offset + LIMIT, total)

  // ── Spinner SVG ──────────────────────────────────────────────────────────────

  const Spinner = () => (
    <svg className="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
    </svg>
  )

  const CloseIcon = () => (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  )

  const selectClass = (active: boolean) =>
    `rounded-md border px-2.5 py-1.5 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer ${
      active
        ? 'border-indigo-400 bg-indigo-50 text-indigo-700'
        : 'border-gray-200 bg-white text-gray-600'
    }`

  return (
    <div>
      {/* ── Sticky header ────────────────────────────────────────────────────── */}
      <div className="sticky top-0 z-20 bg-white border-b border-gray-100 pb-3 space-y-3">

        {/* Error banner */}
        {apiError && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700 mt-5">
            <span>{apiError}</span>
            <button type="button" onClick={() => setApiError(null)} className="shrink-0 text-red-400 hover:text-red-600">
              <CloseIcon />
            </button>
          </div>
        )}

        {/* Success banner */}
        {successMessage && (
          <div className="flex items-center justify-between gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-700 mt-5">
            <span className="flex items-center gap-2">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 6 9 17l-5-5" />
              </svg>
              {successMessage}
            </span>
            <button type="button" onClick={() => setSuccessMessage(null)} className="shrink-0 text-green-400 hover:text-green-600">
              <CloseIcon />
            </button>
          </div>
        )}

        {/* Title row */}
        <div className="flex items-start justify-between gap-4 pt-5">
          <div>
            <h1 className="text-xl font-semibold tracking-tight text-gray-900">Keywords</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              Research, validate, and cluster keywords. Status flow:{' '}
              <span className="font-mono text-xs">raw → validated → clustered</span>
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" />
              </svg>
              Export
            </button>
            {pendingCount > 0 && (
              <button
                type="button"
                disabled={isFetchingMetrics}
                onClick={handleFetchMetrics}
                className="inline-flex items-center gap-1.5 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 hover:bg-amber-100 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isFetchingMetrics ? (
                  <><Spinner />Fetching…</>
                ) : (
                  <>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 2v6h-6M3 12a9 9 0 0 1 15-6.7L21 8M3 22v-6h6M21 12a9 9 0 0 1-15 6.7L3 16" />
                    </svg>
                    Fetch metrics ({pendingCount})
                  </>
                )}
              </button>
            )}
            {rawCount > 0 && (
              <button
                type="button"
                disabled={isValidating}
                onClick={handleValidateAll}
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isValidating ? (
                  <><Spinner />Validating…</>
                ) : (
                  <>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 6 9 17l-5-5" />
                    </svg>
                    Validate all ({rawCount})
                  </>
                )}
              </button>
            )}
            <button
              type="button"
              disabled={isResearching}
              onClick={() => { setResearchError(null); setResearchOpen(true) }}
              className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isResearching ? (
                <><Spinner />Researching…</>
              ) : (
                <>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 3v5M12 16v5M3 12h5M16 12h5M5.6 5.6l3.5 3.5M14.9 14.9l3.5 3.5M18.4 5.6l-3.5 3.5M9.1 14.9l-3.5 3.5" />
                  </svg>
                  Research keywords
                </>
              )}
            </button>
          </div>
        </div>

        {/* KPI strip */}
        {stats && <KpiStrip stats={stats} loading={statsLoading} />}

        {/* Validation progress */}
        {isValidating && (
          <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
            <svg className="animate-spin h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
            </svg>
            <span className="flex-1">
              {validatingCount === 1 && validatingKeyword
                ? <>Validating <strong className="font-semibold">"{validatingKeyword}"</strong> with keyword_validator agent…</>
                : <>Validating {validatingCount} keyword{validatingCount !== 1 ? 's' : ''} with keyword_validator agent…</>
              }
            </span>
            {validateRunId && (
              <span className="font-mono text-xs text-amber-600 shrink-0">
                run {validateRunId.slice(0, 8)}…
              </span>
            )}
          </div>
        )}

        {/* Toolbar */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Search */}
          <div className="relative">
            <svg
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400"
              width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m21 21-4.3-4.3" />
            </svg>
            <input
              className="pl-8 pr-3 py-1.5 rounded-md border border-gray-200 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 w-44"
              placeholder="Search keywords…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {/* Status dropdown */}
          <select
            value={statusFilter}
            onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
            className={selectClass(statusFilter !== 'all')}
          >
            {STATUS_OPTS.map((s) => (
              <option key={s} value={s}>
                {s === 'all' ? 'Status: Any' : s}
              </option>
            ))}
          </select>

          {/* Intent dropdown */}
          <select
            value={intentFilter}
            onChange={(e) => { setIntentFilter(e.target.value); setPage(1) }}
            className={selectClass(intentFilter !== 'all')}
          >
            {INTENT_OPTS.map((i) => (
              <option key={i} value={i}>
                {i === 'all' ? 'Intent: Any' : i}
              </option>
            ))}
          </select>

          {/* Source dropdown */}
          <select
            value={sourceFilter}
            onChange={(e) => { setSourceFilter(e.target.value); setPage(1) }}
            className={selectClass(sourceFilter !== 'all')}
          >
            {SOURCE_OPTS.map((s) => (
              <option key={s} value={s}>
                {s === 'all' ? 'Source: Any' : s === 'dataforseo' ? 'DataForSEO' : 'Pending metrics'}
              </option>
            ))}
          </select>

          {/* Sort dropdown */}
          <select
            value={sortKey}
            onChange={(e) => { setSortKey(e.target.value); setPage(1) }}
            className={selectClass(false)}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>

          {hasFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="text-xs text-gray-400 hover:text-gray-700 px-1 underline underline-offset-2"
            >
              Clear filters
            </button>
          )}

          <span className="ml-auto text-xs text-gray-400 tabular-nums">
            {total > 0 ? `${pageFrom}–${pageTo} of ${total}` : kwLoading ? '…' : '0 keywords'}
          </span>
        </div>
      </div>

      {/* ── Table ────────────────────────────────────────────────────────────── */}
      <div className="mt-4">
        <KeywordsTable
          keywords={keywords}
          loading={kwLoading}
          selectedIds={selectedIds}
          onSelectToggle={toggleSelect}
          onSelectAll={toggleSelectAll}
          onRowClick={setOpenKeyword}
          onValidate={handleValidateRow}
          onCreateContent={handleCreateContent}
          clusters={KW_CLUSTERS}
          validatingId={validatingRowId}
          contentLoadingId={contentLoadingKwId}
        />
      </div>

      {/* ── Pagination ───────────────────────────────────────────────────────── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-xs text-gray-500">
          <span className="tabular-nums">
            Page {page} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
              className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m15 18-6-6 6-6" />
              </svg>
              Prev
            </button>
            {/* Page number buttons — show up to 5 around current */}
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((p) => p === 1 || p === totalPages || Math.abs(p - page) <= 2)
              .reduce<(number | '…')[]>((acc, p, i, arr) => {
                if (i > 0 && typeof arr[i - 1] === 'number' && (arr[i - 1] as number) + 1 < p) acc.push('…')
                acc.push(p)
                return acc
              }, [])
              .map((item, i) =>
                item === '…' ? (
                  <span key={`ellipsis-${i}`} className="px-1 text-gray-300">…</span>
                ) : (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setPage(item as number)}
                    className={`w-7 h-7 rounded-md text-xs font-medium ${
                      item === page
                        ? 'bg-indigo-600 text-white'
                        : 'border border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    {item}
                  </button>
                )
              )}
            <button
              type="button"
              disabled={page === totalPages}
              onClick={() => setPage(page + 1)}
              className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m9 18 6-6-6-6" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* ── Bulk action bar ──────────────────────────────────────────────────── */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-30 flex items-center gap-3 bg-gray-900 text-white rounded-full px-4 py-2.5 shadow-xl text-sm">
          <span className="tabular-nums font-semibold">{selectedIds.size}</span>
          <span className="text-gray-400">selected</span>
          <span className="w-px h-4 bg-gray-600" />
          <button
            type="button"
            onClick={handleValidateSelected}
            disabled={isValidating}
            className="hover:text-indigo-300 disabled:opacity-50"
          >
            Validate selected
          </button>
          <button type="button" className="hover:text-indigo-300">Move to cluster…</button>
          <button type="button" className="hover:text-red-300">Archive</button>
          <span className="w-px h-4 bg-gray-600" />
          <button
            type="button"
            onClick={() => setSelectedIds(new Set())}
            className="p-0.5 hover:text-gray-300"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* ── Drawer ───────────────────────────────────────────────────────────── */}
      <KeywordDrawer
        keyword={openKeyword}
        onClose={() => setOpenKeyword(null)}
        onValidate={(id) => { setOpenKeyword(null); handleValidateRow(id) }}
      />

      {/* ── Research modal ───────────────────────────────────────────────────── */}
      <ResearchModal
        open={researchOpen}
        onClose={() => { setResearchOpen(false); setResearchError(null) }}
        onResearch={handleResearch}
        isLoading={isResearching}
        error={researchError}
      />
    </div>
  )
}
