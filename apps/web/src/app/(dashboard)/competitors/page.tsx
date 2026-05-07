'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Competitor, CompetitorContent } from '@/lib/types'

function timeAgo(iso: string | null): string {
  if (!iso) return 'never'
  const ms = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function CrawlStatus({ lastCrawledAt }: { lastCrawledAt: string | null }) {
  if (!lastCrawledAt) {
    return <span className="text-xs text-gray-400">Never crawled</span>
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-green-700">
      <span className="h-1.5 w-1.5 rounded-full bg-green-500 shrink-0" />
      Done · {timeAgo(lastCrawledAt)}
    </span>
  )
}

function ThreatBar({ value }: { value: number | null }) {
  if (value == null) return <span className="text-xs text-gray-400">—</span>
  const pct = Math.min(Math.max(value * 100, 0), 100)
  const color = pct >= 70 ? 'bg-red-500' : pct >= 40 ? 'bg-amber-400' : 'bg-green-500'
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-gray-100 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="tabular-nums text-xs text-gray-600">{pct.toFixed(0)}</span>
    </div>
  )
}

function normaliseDomain(input: string): string {
  return input
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/^www\./, '')
    .replace(/\/.*$/, '')
}

function AddCompetitorForm({
  onAdd,
  existingDomains,
}: {
  onAdd: (domain: string) => Promise<void>
  existingDomains: string[]
}) {
  const [value, setValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const domain = normaliseDomain(value)
    if (!domain) return
    if (existingDomains.includes(domain)) {
      setError(`${domain} is already being tracked.`)
      return
    }
    setError(null)
    setLoading(true)
    try {
      await onAdd(domain)
      setValue('')
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Failed to add competitor. Check the domain and try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        type="text"
        placeholder="competitor.com"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        className="flex-1 rounded-md border border-gray-200 px-3 py-1.5 text-sm placeholder-gray-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-300"
      />
      <button
        type="submit"
        disabled={loading || !value.trim()}
        className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? (
          <svg className="animate-spin h-3.5 w-3.5" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
          </svg>
        ) : (
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 12h14M12 5l7 7-7 7" />
          </svg>
        )}
        Add
      </button>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </form>
  )
}

export default function CompetitorsPage() {
  const queryClient = useQueryClient()
  const [activeTab, setActiveTab] = useState<'domains' | 'content'>('domains')
  const [contentSearch, setContentSearch] = useState('')

  const { data: competitors = [], isLoading: competitorsLoading } = useQuery({
    queryKey: ['competitors'],
    queryFn: api.competitors.list,
    retry: false,
  })

  const { data: competitorContent = [], isLoading: contentLoading } = useQuery({
    queryKey: ['competitor-content'],
    queryFn: () => api.competitorContent.list({ order: 'desc', limit: 100 }),
    retry: false,
    enabled: activeTab === 'content',
  })

  const addMutation = useMutation({
    mutationFn: (domain: string) => api.competitors.add(domain),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['competitors'] }),
  })

  const removeMutation = useMutation({
    mutationFn: (id: string) => api.competitors.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['competitors'] }),
  })

  const filteredContent = contentSearch
    ? competitorContent.filter(
        (c) =>
          c.title?.toLowerCase().includes(contentSearch.toLowerCase()) ||
          c.url.toLowerCase().includes(contentSearch.toLowerCase()) ||
          c.domain?.toLowerCase().includes(contentSearch.toLowerCase())
      )
    : competitorContent

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-gray-900">Competitors</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          Track competitor domains and monitor their content
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-0.5 rounded-lg bg-gray-100 p-1 w-fit">
        {(['domains', 'content'] as const).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => {
              setActiveTab(tab)
              if (tab !== activeTab) setContentSearch('')
            }}
            className={`rounded-md px-4 py-1.5 text-xs font-medium capitalize transition-colors ${
              activeTab === tab
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab === 'domains' ? `Domains (${competitors.length})` : 'Content'}
          </button>
        ))}
      </div>

      {activeTab === 'domains' && (
        <div className="space-y-4">
          {/* Add form */}
          <div className="rounded-lg border border-gray-200 bg-white px-5 py-4">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">
              Add Competitor Domain
            </p>
            <AddCompetitorForm
              onAdd={(domain) => addMutation.mutateAsync(domain).then(() => {})}
              existingDomains={competitors.map((c) => normaliseDomain(c.domain))}
            />
          </div>

          {/* Domains list */}
          {competitorsLoading ? (
            <div className="space-y-2">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-14 animate-pulse rounded-lg bg-gray-100" />
              ))}
            </div>
          ) : competitors.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm text-gray-400">
                No competitors tracked yet. Add a domain above to start monitoring.
              </p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-100 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Domain</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden sm:table-cell">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden md:table-cell">Threat Score</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden md:table-cell">Keyword Overlap</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {competitors.map((c) => (
                    <tr key={c.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <a
                          href={`https://${c.domain}`}
                          target="_blank"
                          rel="noreferrer"
                          className="font-medium text-indigo-600 hover:underline"
                        >
                          {c.domain}
                        </a>
                      </td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <CrawlStatus lastCrawledAt={c.last_crawled_at ?? null} />
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        <ThreatBar value={c.threat_score ?? null} />
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell">
                        {c.keyword_overlap != null ? (
                          <span className="text-xs text-gray-600">
                            {c.keyword_overlap} keywords
                          </span>
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => removeMutation.mutate(c.id)}
                          disabled={removeMutation.isPending}
                          className="text-xs text-gray-400 hover:text-red-500 transition-colors"
                          title="Remove competitor"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polyline points="3 6 5 6 21 6" />
                            <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
                            <path d="M10 11v6M14 11v6" />
                            <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'content' && (
        <div className="space-y-4">
          {/* Search */}
          <div className="relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <input
              type="text"
              placeholder="Search competitor content…"
              value={contentSearch}
              onChange={(e) => setContentSearch(e.target.value)}
              className="w-full rounded-md border border-gray-200 py-1.5 pl-8 pr-3 text-sm placeholder-gray-400 focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-300"
            />
          </div>

          {contentLoading ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-12 animate-pulse rounded bg-gray-100" />
              ))}
            </div>
          ) : competitorContent.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm text-gray-400">
                No competitor content extracted yet. Run competitor monitor to start crawling.
              </p>
            </div>
          ) : filteredContent.length === 0 ? (
            <div className="py-12 text-center">
              <p className="text-sm text-gray-400">No results match your search.</p>
            </div>
          ) : (
            <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
              <table className="min-w-full divide-y divide-gray-100 text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Title / URL</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden sm:table-cell">Domain</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden md:table-cell">Words</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500">Threat</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 hidden lg:table-cell">Keyword Overlap</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {filteredContent.map((item) => (
                    <tr key={item.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 max-w-xs">
                        <p className="font-medium text-gray-900 text-xs line-clamp-1">
                          {item.title ?? '(no title)'}
                        </p>
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[11px] text-gray-400 hover:text-indigo-600 font-mono truncate block"
                        >
                          {item.url}
                        </a>
                      </td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <span className="text-xs text-gray-500">{item.domain ?? '—'}</span>
                      </td>
                      <td className="px-4 py-3 hidden md:table-cell tabular-nums text-xs text-gray-500">
                        {item.word_count?.toLocaleString() ?? '—'}
                      </td>
                      <td className="px-4 py-3">
                        <ThreatBar value={item.threat_score} />
                      </td>
                      <td className="px-4 py-3 hidden lg:table-cell">
                        {item.keywords_overlap && item.keywords_overlap.length > 0 ? (
                          <div className="flex flex-wrap gap-1">
                            {item.keywords_overlap.slice(0, 3).map((kw) => (
                              <span
                                key={kw}
                                className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-600"
                              >
                                {kw}
                              </span>
                            ))}
                            {item.keywords_overlap.length > 3 && (
                              <span className="text-[10px] text-gray-400">
                                +{item.keywords_overlap.length - 3}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-gray-400">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
