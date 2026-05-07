'use client'

import { useState, useMemo, useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, axiosInstance } from '@/lib/api'
import { mockKeywords, mockKeywordStats, KW_CLUSTERS } from '@/lib/mocks'
import type { KeywordRow } from '@/lib/types'
import { KpiStrip } from './components/KpiStrip'
import { KeywordsTable } from './components/KeywordsTable'
import { KeywordDrawer } from './components/KeywordDrawer'
import { ResearchModal } from './components/ResearchModal'

const STATUS_FILTERS = ['all', 'raw', 'validated', 'clustered', 'archived'] as const
const INTENT_FILTERS = ['all', 'commercial', 'informational', 'transactional', 'navigational'] as const

export default function KeywordsPage() {
  const queryClient = useQueryClient()

  // Filter state
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [intentFilter, setIntentFilter] = useState<string>('all')
  const [search, setSearch] = useState('')

  // Selection state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Drawer state
  const [openKeyword, setOpenKeyword] = useState<KeywordRow | null>(null)

  // Modal state
  const [researchOpen, setResearchOpen] = useState(false)

  // In-flight run IDs
  const [researchRunId, setResearchRunId] = useState<string | null>(null)
  const [validateRunId, setValidateRunId] = useState<string | null>(null)
  const [validatingCount, setValidatingCount] = useState(0)

  // Research state
  const [isResearching, setIsResearching] = useState(false)
  const [researchError, setResearchError] = useState<string | null>(null)

  // Feedback banners
  const [successMessage, setSuccessMessage] = useState<string | null>(null)

  // ── Queries ─────────────────────────────────────────────────────────────────
  // initialData + initialDataUpdatedAt:0 keeps mock data in cache even when
  // the API fetch fails (unlike placeholderData which clears on error).
  // Filtering is done client-side so every filtered view has data immediately.

  const { data: allKeywords = mockKeywords, isLoading: kwLoading } = useQuery({
    queryKey: ['keywords'],
    queryFn: () => api.keywords.list({ limit: 500 }),
    initialData: mockKeywords,
    initialDataUpdatedAt: 0,
  })

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

  // ── Side effects ─────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!researchRun) return

    if (researchRun.status === 'success') {
      setIsResearching(false)
      setResearchRunId(null)
      setResearchError(null)
      queryClient.invalidateQueries({ queryKey: ['keywords'] })
      queryClient.invalidateQueries({ queryKey: ['keyword-stats'] })
      setSuccessMessage('Keywords added successfully')
    }

    if (researchRun.status === 'failed') {
      setIsResearching(false)
      setResearchRunId(null)
      setResearchError(
        researchRun.error ?? 'Keyword research failed. Check Settings → Integrations.'
      )
      setResearchOpen(true)
    }

    if (researchRun.status === 'partial') {
      setIsResearching(false)
      setResearchRunId(null)
      setResearchError(
        researchRun.error ?? 'Research completed with warnings — fewer keywords than expected.'
      )
      queryClient.invalidateQueries({ queryKey: ['keywords'] })
      queryClient.invalidateQueries({ queryKey: ['keyword-stats'] })
      setResearchOpen(true)
    }
  }, [researchRun?.status, queryClient])

  useEffect(() => {
    if (!validateRun) return
    if (validateRun.status === 'success') {
      setValidateRunId(null)
      setValidatingCount(0)
      queryClient.invalidateQueries({ queryKey: ['keywords'] })
      queryClient.invalidateQueries({ queryKey: ['keyword-stats'] })
      setSuccessMessage('Validation complete — keywords updated')
    }
    if (validateRun.status === 'failed') {
      setValidateRunId(null)
      setValidatingCount(0)
      setApiError(validateRun.error ?? 'Validation failed')
    }
  }, [validateRun?.status, queryClient])

  // ── Filtered rows (client-side, matches prototype pattern) ──────────────────

  const rows = useMemo(() => {
    let r = allKeywords
    if (statusFilter !== 'all') r = r.filter((k) => k.status === statusFilter)
    if (intentFilter !== 'all') r = r.filter((k) => k.intent === intentFilter)
    if (search.trim()) {
      const q = search.toLowerCase()
      r = r.filter((k) => k.keyword.toLowerCase().includes(q))
    }
    return r
  }, [allKeywords, statusFilter, intentFilter, search])

  // ── Selection helpers ────────────────────────────────────────────────────────

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (rows.every((r) => selectedIds.has(r.id))) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(rows.map((r) => r.id)))
    }
  }

  // ── Action handlers ──────────────────────────────────────────────────────────

  const [apiError, setApiError] = useState<string | null>(null)

  const handleResearch = async (seed: string) => {
    setApiError(null)
    setResearchError(null)
    try {
      const { run_id } = await api.keywords.research(seed)
      setResearchRunId(run_id)
      setIsResearching(true)
      setResearchOpen(false)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Research failed — is the API running?'
      setResearchError(msg)
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
    try {
      const { run_id } = await api.keywords.validate([keyword_id])
      setValidateRunId(run_id)
      setValidatingCount(1)
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Validation failed')
    }
  }

  const handleCreateContent = async (keyword: KeywordRow) => {
    setApiError(null)
    setSuccessMessage(null)
    try {
      // Find the opportunity for this keyword then trigger content_director
      const opportunities = await api.opportunities.list({ limit: 200 })
      const opp = opportunities.find((o: any) => o.keyword_id === keyword.id)
      if (!opp) {
        setApiError(`No opportunity found for "${keyword.keyword}" — run opportunity scorer first`)
        return
      }
      await axiosInstance.post('/api/v1/agents/content_director/run', {
        params: { opportunity_id: opp.id },
      })
      setSuccessMessage(`Content pipeline started for "${keyword.keyword}" — check Content page in ~15 min`)
    } catch (err) {
      setApiError(err instanceof Error ? err.message : 'Failed to start content pipeline')
    }
  }

  const clearFilters = () => {
    setStatusFilter('all')
    setIntentFilter('all')
    setSearch('')
  }

  const hasFilters =
    statusFilter !== 'all' || intentFilter !== 'all' || search.trim() !== ''

  // isResearching is driven by explicit state, not inferred from run status,
  // so the button stays disabled while the run ID is being fetched.
  const isValidating = validateRun?.status === 'running' || !!validateRunId
  const rawCount = stats?.raw ?? 0

  return (
    <div className="space-y-5">
      {/* Error banner */}
      {apiError && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700">
          <span>{apiError}</span>
          <button type="button" onClick={() => setApiError(null)} className="shrink-0 text-red-400 hover:text-red-600">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Success banner */}
      {successMessage && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-green-200 bg-green-50 px-4 py-2.5 text-sm text-green-700">
          <span className="flex items-center gap-2">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 6 9 17l-5-5" />
            </svg>
            {successMessage}
          </span>
          <button type="button" onClick={() => setSuccessMessage(null)} className="shrink-0 text-green-400 hover:text-green-600">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Page header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-gray-900">
            Keywords
          </h1>
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
          {rawCount > 0 && (
            <button
              type="button"
              disabled={isValidating}
              onClick={handleValidateAll}
              className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isValidating ? (
                <>
                  <svg className="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
                  </svg>
                  Validating…
                </>
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
            onClick={() => setResearchOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isResearching ? (
              <>
                <svg className="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
                </svg>
                Researching…
              </>
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

      {/* Validation progress banner */}
      {isValidating && (
        <div className="flex items-center gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800">
          <svg className="animate-spin h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
          </svg>
          <span className="flex-1">
            Validating {validatingCount} keyword{validatingCount !== 1 ? 's' : ''} with keyword_validator agent…
            {validatingCount > 1 && (
              <span className="text-amber-600">
                {' '}Est. {Math.ceil(validatingCount * 6 / 60)} min on Ollama.
              </span>
            )}
          </span>
          {validateRunId && (
            <span className="font-mono text-xs text-amber-600 shrink-0">
              run {validateRunId.slice(0, 8)}…
            </span>
          )}
        </div>
      )}

      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
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
              className="pl-8 pr-3 py-1.5 rounded-md border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 w-48"
              placeholder="Search keywords…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {/* Status filter */}
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
            onClick={() => {
              const idx = STATUS_FILTERS.indexOf(statusFilter as typeof STATUS_FILTERS[number])
              setStatusFilter(STATUS_FILTERS[(idx + 1) % STATUS_FILTERS.length])
            }}
          >
            Status:{' '}
            <strong className="font-semibold">
              {statusFilter === 'all' ? 'Any' : statusFilter}
            </strong>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>

          {/* Intent filter */}
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-md border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
            onClick={() => {
              const idx = INTENT_FILTERS.indexOf(intentFilter as typeof INTENT_FILTERS[number])
              setIntentFilter(INTENT_FILTERS[(idx + 1) % INTENT_FILTERS.length])
            }}
          >
            Intent:{' '}
            <strong className="font-semibold">
              {intentFilter === 'all' ? 'Any' : intentFilter}
            </strong>
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>

          {hasFilters && (
            <button
              type="button"
              onClick={clearFilters}
              className="text-xs text-gray-500 hover:text-gray-700 px-1"
            >
              Clear
            </button>
          )}
        </div>

        <div className="flex items-center gap-2 text-xs text-gray-400 tabular-nums">
          {rows.length} of {allKeywords.length}
        </div>
      </div>

      {/* Table */}
      <KeywordsTable
        keywords={rows}
        loading={kwLoading}
        selectedIds={selectedIds}
        onSelectToggle={toggleSelect}
        onSelectAll={toggleSelectAll}
        onRowClick={setOpenKeyword}
        onValidate={handleValidateRow}
        onCreateContent={handleCreateContent}
        clusters={KW_CLUSTERS}
      />

      {/* Bulk action bar */}
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
          <button type="button" className="hover:text-indigo-300">
            Move to cluster…
          </button>
          <button type="button" className="hover:text-red-300">
            Archive
          </button>
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

      {/* Drawer */}
      <KeywordDrawer
        keyword={openKeyword}
        onClose={() => setOpenKeyword(null)}
        onValidate={(id) => {
          setOpenKeyword(null)
          handleValidateRow(id)
        }}
      />

      {/* Research modal */}
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
