'use client'

import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { KeywordRow, KeywordDetail } from '@/lib/types'
import { KW_CLUSTERS } from '@/lib/mocks'
import { Sparkline } from './Sparkline'
import {
  StatusBadge,
  IntentBadge,
  DataSourceBadge,
  Difficulty,
} from './KeywordsTable'

interface KeywordDrawerProps {
  keyword: KeywordRow | null
  onClose: () => void
  onValidate?: (id: string) => void
  onGenerateContent?: (id: string) => void
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function KeywordDrawer({
  keyword,
  onClose,
  onValidate,
  onGenerateContent,
}: KeywordDrawerProps) {
  const isRealId = keyword ? UUID_RE.test(keyword.id) : false

  const { data: detail } = useQuery<KeywordDetail>({
    queryKey: ['keyword-detail', keyword?.id],
    queryFn: () => api.keywords.detail(keyword!.id),
    enabled: !!keyword && isRealId,
    staleTime: 60_000,
  })

  // Close on Escape
  useEffect(() => {
    if (!keyword) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [keyword, onClose])

  const open = !!keyword

  const trendData = detail?.trend_data ?? []
  const cluster = keyword
    ? KW_CLUSTERS.find(
        (c) => c.id === keyword.cluster || c.id === keyword.cluster_id
      )
    : null
  const related = keyword
    ? (detail
        ? [] // real data: no related yet
        : (KW_CLUSTERS.length > 0
            ? [] // would need full list to compute related
            : [])
      )
    : []

  const recentRuns = detail?.recent_runs ?? []

  return (
    <>
      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-40 bg-black/20 transition-opacity duration-200 ${
          open ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
      />

      {/* Drawer panel */}
      <div
        className={`fixed top-0 right-0 z-50 h-full w-[420px] max-w-full bg-white border-l border-gray-200 shadow-xl flex flex-col transition-transform duration-200 ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {keyword && (
          <>
            {/* Head */}
            <div className="px-5 pt-5 pb-4 border-b border-gray-100">
              <div className="flex justify-between items-start gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    {keyword.status === 'clustered' && cluster ? (
                      <>
                        <span
                          className="inline-block w-2 h-2 rounded-sm shrink-0"
                          style={{ background: cluster.color }}
                        />
                        <span className="text-xs text-gray-400">
                          {cluster.name}
                        </span>
                      </>
                    ) : (
                      <span className="text-xs text-gray-400">
                        Not yet clustered
                      </span>
                    )}
                  </div>
                  <h2 className="text-lg font-semibold tracking-tight text-gray-900 m-0">
                    {keyword.keyword}
                  </h2>
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    <StatusBadge status={keyword.status} />
                    <IntentBadge intent={keyword.intent} />
                    <DataSourceBadge source={keyword.data_source} />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  className="p-1 rounded-md hover:bg-gray-100 text-gray-400 hover:text-gray-600 shrink-0"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M18 6 6 18M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
              {/* Stat grid */}
              <div className="grid grid-cols-2 gap-3">
                {[
                  {
                    label: 'Volume',
                    value: keyword.volume != null
                      ? `${keyword.volume.toLocaleString()} /mo`
                      : '—',
                  },
                  {
                    label: 'Difficulty',
                    node: <Difficulty value={keyword.kd} />,
                  },
                  {
                    label: 'CPC',
                    value: keyword.cpc != null ? `$${keyword.cpc.toFixed(2)}` : '—',
                  },
                ].map((cell) => (
                  <div
                    key={cell.label}
                    className="bg-gray-50 rounded-lg px-3 py-2.5"
                  >
                    <div className="text-xs text-gray-400 font-medium mb-1">
                      {cell.label}
                    </div>
                    <div className="text-sm font-semibold text-gray-800">
                      {cell.node ?? cell.value}
                    </div>
                  </div>
                ))}
              </div>

              {/* Validator reasoning */}
              {keyword.reason && (
                <div>
                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Validator reasoning
                  </div>
                  <div className="bg-indigo-50 border-l-2 border-indigo-400 rounded-r-md px-3 py-2.5 text-sm text-gray-700 leading-relaxed">
                    {keyword.reason}
                    <div className="text-xs text-gray-400 mt-1.5 font-mono">
                      via keyword_validator
                    </div>
                  </div>
                </div>
              )}

              {/* 12-month sparkline */}
              {trendData.length >= 2 && (
                <div>
                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Search volume — last 12 months
                  </div>
                  <div className="border border-gray-200 rounded-lg p-3">
                    <Sparkline
                      data={trendData}
                      width={360}
                      height={64}
                      color="#534AB7"
                    />
                    <div className="flex justify-between mt-2 text-xs text-gray-400 font-mono">
                      <span>May &apos;25</span>
                      <span>Apr &apos;26</span>
                    </div>
                  </div>
                </div>
              )}

              {/* Linked content / Next step */}
              {keyword.url ? (
                <div>
                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Linked content
                  </div>
                  <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
                    <div className="flex items-center justify-between px-3 py-2.5 gap-3">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-gray-800 truncate">
                          {keyword.url}
                        </div>
                        <div className="text-xs text-gray-400 mt-0.5">
                          {keyword.contentCount ?? 0} piece
                          {(keyword.contentCount ?? 0) === 1 ? '' : 's'}
                        </div>
                      </div>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-gray-400">
                        <path d="M15 3h6v6M10 14 21 3M21 14v7H3V3h7" />
                      </svg>
                    </div>
                  </div>
                </div>
              ) : (keyword.status === 'validated' ||
                  keyword.status === 'clustered') ? (
                <div>
                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Next step
                  </div>
                  <div className="border border-dashed border-indigo-200 bg-indigo-50 rounded-lg px-3 py-3 flex items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-indigo-700">
                        No content yet
                      </div>
                      <div className="text-xs text-indigo-500 mt-0.5">
                        Dispatch content_director to draft an article and
                        LinkedIn post.
                      </div>
                    </div>
                    <button
                      type="button"
                      className="shrink-0 inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
                      onClick={() => onGenerateContent?.(keyword.id)}
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M12 3v5M12 16v5M3 12h5M16 12h5M5.6 5.6l3.5 3.5M14.9 14.9l3.5 3.5M18.4 5.6l-3.5 3.5M9.1 14.9l-3.5 3.5" />
                      </svg>
                      Generate
                    </button>
                  </div>
                </div>
              ) : null}

              {/* Related in cluster (mock data only) */}
              {related.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Related in cluster
                  </div>
                  <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
                    {related.map((r: KeywordRow) => (
                      <div
                        key={r.id}
                        className="flex items-center justify-between px-3 py-2.5 gap-3"
                      >
                        <div className="min-w-0">
                          <div className="text-sm text-gray-800 truncate">
                            {r.keyword}
                          </div>
                          <div className="text-xs text-gray-400 mt-0.5 tabular-nums">
                            {r.volume?.toLocaleString()} vol · KD{' '}
                            {r.kd?.toFixed(1)} · ${r.cpc?.toFixed(2)}
                          </div>
                        </div>
                        <StatusBadge status={r.status} />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Recent agent runs */}
              {recentRuns.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                    Recent agent runs
                  </div>
                  <div className="border border-gray-200 rounded-lg divide-y divide-gray-100">
                    {recentRuns.map((r) => (
                      <div
                        key={r.run_id}
                        className="flex items-center justify-between px-3 py-2.5 gap-3"
                      >
                        <div>
                          <div className="text-xs font-mono text-gray-700">
                            {r.agent_name}
                          </div>
                          <div className="text-xs text-gray-400 mt-0.5">
                            ${r.cost_usd.toFixed(3)} ·{' '}
                            {r.duration_ms != null
                              ? `${(r.duration_ms / 1000).toFixed(1)}s`
                              : '—'}
                          </div>
                        </div>
                        <span className="inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium bg-green-50 text-green-700">
                          <span className="inline-block w-1.5 h-1.5 rounded-full bg-green-500" />
                          {r.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-5 py-3 border-t border-gray-100 flex items-center justify-between gap-2">
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
                </svg>
                Edit
              </button>
              <div className="flex gap-2">
                {keyword.status === 'raw' && (
                  <button
                    type="button"
                    className="inline-flex items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50"
                    onClick={() => onValidate?.(keyword.id)}
                  >
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 6 9 17l-5-5" />
                    </svg>
                    Validate
                  </button>
                )}
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700"
                  onClick={() => onGenerateContent?.(keyword.id)}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 3v5M12 16v5M3 12h5M16 12h5M5.6 5.6l3.5 3.5M14.9 14.9l3.5 3.5M18.4 5.6l-3.5 3.5M9.1 14.9l-3.5 3.5" />
                  </svg>
                  Generate content
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  )
}
