'use client'

import { useRef } from 'react'
import type { KeywordRow, KwCluster } from '@/lib/types'

// ── Badge components ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: KeywordRow['status'] }) {
  const map = {
    raw:             { bg: 'bg-gray-100',   text: 'text-gray-600',   dot: '#9A9AA3', label: 'Raw' },
    validated:       { bg: 'bg-purple-50',  text: 'text-purple-700', dot: '#534AB7', label: 'Validated' },
    clustered:       { bg: 'bg-green-50',   text: 'text-green-700',  dot: '#16A34A', label: 'Clustered' },
    archived:        { bg: 'bg-gray-100',   text: 'text-gray-400',   dot: '#6B6B73', label: 'Archived' },
    pending_metrics: { bg: 'bg-blue-50',    text: 'text-blue-700',   dot: '#3B82F6', label: 'Pending metrics' },
  }
  const m = map[status] ?? map.raw
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${m.bg} ${m.text} ${status === 'archived' ? 'opacity-70' : ''}`}
    >
      <span
        className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
        style={{ background: m.dot }}
      />
      {m.label}
    </span>
  )
}

function IntentBadge({ intent }: { intent: KeywordRow['intent'] }) {
  if (!intent) return <span className="text-gray-400 text-xs">—</span>
  const map: Record<string, { bg: string; text: string }> = {
    commercial:    { bg: 'bg-green-50',  text: 'text-green-700' },
    informational: { bg: 'bg-blue-50',   text: 'text-blue-700' },
    transactional: { bg: 'bg-amber-50',  text: 'text-amber-700' },
    navigational:  { bg: 'bg-gray-100',  text: 'text-gray-600' },
  }
  const m = map[intent] ?? { bg: 'bg-gray-100', text: 'text-gray-600' }
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${m.bg} ${m.text}`}
    >
      {intent.charAt(0).toUpperCase() + intent.slice(1)}
    </span>
  )
}

function DataSourceBadge({ source }: { source: KeywordRow['data_source'] }) {
  if (source === 'dataforseo' || source === 'keywords_everywhere') {
    const label = source === 'dataforseo' ? 'DataForSEO' : 'KW Everywhere'
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium bg-green-50 text-green-700"
        title={`Live data from ${label}`}
      >
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500 shrink-0" />
        Live
      </span>
    )
  }
  if (source === 'estimated') {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium bg-blue-50 text-blue-700"
        title="Estimated via Anchor-Scale (Tier 3). True-up required when real API restores."
      >
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-400 shrink-0" />
        Estimated
      </span>
    )
  }
  if (source === 'pending' || source === 'llm_estimate') {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium bg-amber-50 text-amber-700"
        title="Metrics unavailable. Use Fetch metrics to backfill from DataForSEO."
      >
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
        Metrics pending
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium bg-gray-100 text-gray-500"
      title={source}
    >
      <span className="inline-block w-1.5 h-1.5 rounded-full bg-gray-400 shrink-0" />
      {source}
    </span>
  )
}

// ── KD bar: 0-10 scale ────────────────────────────────────────────────────────

function Difficulty({ value }: { value: number | null }) {
  if (value == null) return <span className="text-gray-300 text-xs">—</span>
  const pct = Math.min(100, Math.max(4, value * 10))
  const color =
    value < 4 ? '#16A34A'
    : value < 7 ? '#CA8A04'
    : value <= 9 ? '#EA580C'
    : '#DC2626'
  const textColor =
    value < 4 ? 'text-green-700'
    : value < 7 ? 'text-yellow-700'
    : value <= 9 ? 'text-orange-600'
    : 'text-red-700'
  return (
    <span className="inline-flex items-center gap-2">
      <span className="inline-block w-10 h-1 rounded-full bg-gray-200 overflow-hidden">
        <span
          className="block h-full rounded-full"
          style={{ width: `${pct}%`, background: color }}
        />
      </span>
      <span className={`tabular-nums text-xs font-medium ${textColor}`}>
        {value.toFixed(1)}
      </span>
    </span>
  )
}

// ── Checkbox ──────────────────────────────────────────────────────────────────

function Checkbox({
  state,
  onClick,
}: {
  state: 'checked' | 'indet' | 'none'
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        onClick?.()
      }}
      className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors ${
        state === 'checked'
          ? 'bg-indigo-600 border-indigo-600'
          : state === 'indet'
          ? 'bg-indigo-100 border-indigo-400'
          : 'border-gray-300 hover:border-gray-400'
      }`}
    >
      {state === 'checked' && (
        <svg width="9" height="9" viewBox="0 0 12 12" fill="none">
          <path d="M2 6l3 3 5-5" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
      {state === 'indet' && (
        <span className="block w-2 h-0.5 bg-indigo-600 rounded" />
      )}
    </button>
  )
}

// ── Main table ────────────────────────────────────────────────────────────────

interface KeywordsTableProps {
  keywords: KeywordRow[]
  loading: boolean
  selectedIds: Set<string>
  onSelectToggle: (id: string) => void
  onSelectAll: () => void
  onRowClick: (keyword: KeywordRow) => void
  onValidate?: (id: string) => void
  clusters?: KwCluster[]
  validatingId?: string | null
}

export function KeywordsTable({
  keywords,
  loading,
  selectedIds,
  onSelectToggle,
  onSelectAll,
  onRowClick,
  onValidate,
  clusters = [],
  validatingId = null,
}: KeywordsTableProps) {
  const tableRef = useRef<HTMLDivElement>(null)
  const allChecked =
    keywords.length > 0 && keywords.every((k) => selectedIds.has(k.id))
  const anyChecked = keywords.some((k) => selectedIds.has(k.id))
  const allState = allChecked ? 'checked' : anyChecked ? 'indet' : 'none'

  if (loading) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="flex items-center justify-center py-16 text-sm text-gray-400">
          <svg className="animate-spin h-4 w-4 mr-2 text-gray-400" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
          </svg>
          Loading keywords…
        </div>
      </div>
    )
  }

  if (keywords.length === 0) {
    return (
      <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
        <div className="flex flex-col items-center py-16 gap-3 text-center">
          <div className="p-2.5 rounded-xl bg-indigo-50 text-indigo-600">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20.59 13.41 12 22 2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82Z" />
              <circle cx="7" cy="7" r="1.4" fill="currentColor" />
            </svg>
          </div>
          <div>
            <p className="font-medium text-gray-800 text-sm">No keywords match your filters</p>
            <p className="text-xs text-gray-400 mt-1">
              Try clearing filters, or run keyword_research to surface fresh opportunities.
            </p>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      ref={tableRef}
      className="bg-white border border-gray-200 rounded-lg overflow-hidden"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-gray-50">
              <th className="w-10 px-3 py-3">
                <Checkbox state={allState} onClick={onSelectAll} />
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                Keyword
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                Source
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                Intent
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wide">
                Volume
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                KD
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wide">
                CPC
              </th>
              <th className="w-8 px-3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {keywords.map((kw) => {
              const cluster = clusters.find((c) => c.id === kw.cluster || c.id === kw.cluster_id)
              const isSel = selectedIds.has(kw.id)
              const isValidatingRow = validatingId === kw.id
              return (
                <tr
                  key={kw.id}
                  className={`transition-colors cursor-pointer ${
                    isValidatingRow
                      ? 'bg-amber-50 hover:bg-amber-50'
                      : isSel
                      ? 'bg-indigo-50 hover:bg-indigo-50'
                      : 'hover:bg-gray-50'
                  }`}
                  onClick={() => onRowClick(kw)}
                >
                  <td className="w-10 px-3 py-3">
                    <Checkbox
                      state={isSel ? 'checked' : 'none'}
                      onClick={() => onSelectToggle(kw.id)}
                    />
                  </td>
                  <td className="px-4 py-3 max-w-xs">
                    <div className="font-medium text-gray-900 truncate">
                      {kw.keyword}
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5 flex items-center gap-1.5">
                      {kw.status === 'clustered' && cluster ? (
                        <>
                          <span
                            className="inline-block w-2 h-2 rounded-sm shrink-0"
                            style={{ background: cluster.color }}
                          />
                          <span>{cluster.name}</span>
                        </>
                      ) : (kw.contentCount ?? 0) > 0 ? (
                        <span>
                          {kw.contentCount} content piece
                          {kw.contentCount === 1 ? '' : 's'}
                        </span>
                      ) : (
                        <span>No content yet</span>
                      )}
                      {' · '}
                      <span className="font-mono">{kw.source_agent}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <DataSourceBadge source={kw.data_source} />
                  </td>
                  <td className="px-4 py-3">
                    {isValidatingRow ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium bg-amber-100 text-amber-700">
                        <svg className="animate-spin h-3 w-3 shrink-0" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
                        </svg>
                        Validating…
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1">
                        <StatusBadge status={kw.status} />
                        {kw.status === 'validated' && kw.data_source === 'estimated' && (
                          <span className="text-xs text-blue-500 font-normal">(est.)</span>
                        )}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <IntentBadge intent={kw.intent} />
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-sm">
                    {kw.volume != null ? kw.volume.toLocaleString() : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <Difficulty value={kw.kd} />
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-sm">
                    {kw.cpc != null ? `$${kw.cpc.toFixed(2)}` : '—'}
                  </td>
                  <td className="px-3 py-3 text-right">
                    {!isValidatingRow && kw.status === 'raw' && onValidate && (
                      <button
                        type="button"
                        onClick={(e) => { e.stopPropagation(); onValidate(kw.id) }}
                        className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-50 hover:border-indigo-300 hover:text-indigo-600 transition-colors"
                      >
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 6 9 17l-5-5" />
                        </svg>
                        Validate
                      </button>
                    )}
                    {!isValidatingRow && kw.status === 'validated' && (
                      <button
                        type="button"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex items-center gap-1 rounded border border-indigo-200 bg-indigo-50 px-2 py-1 text-xs font-medium text-indigo-600 hover:bg-indigo-100 transition-colors"
                      >
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M12 3v5M12 16v5M3 12h5M16 12h5M5.6 5.6l3.5 3.5M14.9 14.9l3.5 3.5M18.4 5.6l-3.5 3.5M9.1 14.9l-3.5 3.5" />
                        </svg>
                        Create content
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export { StatusBadge, IntentBadge, DataSourceBadge, Difficulty }
