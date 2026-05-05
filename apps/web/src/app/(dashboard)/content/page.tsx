'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Badge, statusBadgeVariant } from '@/components/ui/badge'
import type { Article, ArticleStatus } from '@/lib/types'

const STATUS_TABS: { value: ArticleStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'draft', label: 'Drafts' },
  { value: 'review', label: 'In Review' },
  { value: 'approved', label: 'Approved' },
  { value: 'published', label: 'Published' },
]

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function ScorePill({ label, value }: { label: string; value: number | null }) {
  if (value == null) return null
  const pct = Math.round(value * 100)
  const color = pct >= 70 ? 'text-green-700 bg-green-50' : pct >= 40 ? 'text-amber-700 bg-amber-50' : 'text-red-700 bg-red-50'
  return (
    <span className={`inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium ${color}`}>
      {label} {pct}
    </span>
  )
}

function ArticleDrawer({
  article,
  onClose,
  onStatusChange,
}: {
  article: Article
  onClose: () => void
  onStatusChange: (id: string, status: ArticleStatus) => void
}) {
  const nextStatus: Partial<Record<ArticleStatus, ArticleStatus>> = {
    draft: 'review',
    review: 'approved',
    approved: 'published',
  }
  const actionLabel: Partial<Record<ArticleStatus, string>> = {
    draft: 'Submit for Review',
    review: 'Approve',
    approved: 'Mark Published',
  }

  return (
    <div className="fixed inset-0 z-40 flex">
      {/* Backdrop */}
      <div
        className="flex-1 bg-black/20"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Panel */}
      <div className="w-full max-w-2xl bg-white shadow-xl flex flex-col overflow-hidden">
        <div className="flex items-start justify-between border-b border-gray-200 px-6 py-4">
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">
              {article.keyword ?? 'Article'}
            </p>
            <h2 className="mt-0.5 text-base font-semibold text-gray-900 leading-snug">
              {article.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="ml-4 shrink-0 text-gray-400 hover:text-gray-600"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Meta row */}
        <div className="flex flex-wrap items-center gap-2 px-6 py-3 border-b border-gray-100 bg-gray-50">
          <Badge variant={statusBadgeVariant(article.status)}>{article.status}</Badge>
          {article.word_count != null && (
            <span className="text-xs text-gray-500">{article.word_count.toLocaleString()} words</span>
          )}
          <ScorePill label="Voice" value={article.brand_voice_score} />
          <ScorePill label="SEO" value={article.seo_score} />
          <span className="text-xs text-gray-400 ml-auto">{timeAgo(article.created_at)}</span>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {article.body_html ? (
            <div
              className="prose prose-sm max-w-none text-gray-700"
              dangerouslySetInnerHTML={{ __html: article.body_html }}
            />
          ) : (
            <p className="text-sm text-gray-400 italic">No body content available.</p>
          )}
        </div>

        {/* Footer actions */}
        {article.status !== 'published' && nextStatus[article.status] && (
          <div className="border-t border-gray-200 px-6 py-4 flex items-center justify-between">
            {article.published_url && (
              <a
                href={article.published_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-indigo-600 hover:underline"
              >
                View on site →
              </a>
            )}
            <button
              type="button"
              onClick={() => {
                const next = nextStatus[article.status]
                if (next) onStatusChange(article.id, next)
              }}
              className="ml-auto inline-flex items-center rounded-md bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-indigo-700"
            >
              {actionLabel[article.status]}
            </button>
          </div>
        )}
        {article.status === 'published' && article.published_url && (
          <div className="border-t border-gray-200 px-6 py-4">
            <a
              href={article.published_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-indigo-600 hover:underline"
            >
              View published article →
            </a>
          </div>
        )}
      </div>
    </div>
  )
}

export default function ContentPage() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<ArticleStatus | 'all'>('all')
  const [openArticle, setOpenArticle] = useState<Article | null>(null)

  const { data: articles = [], isLoading } = useQuery({
    queryKey: ['articles', statusFilter],
    queryFn: () =>
      api.articles.list({
        status: statusFilter === 'all' ? undefined : statusFilter,
        limit: 100,
      }),
    retry: false,
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ArticleStatus }) =>
      api.articles.update(id, { status }),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['articles'] })
      setOpenArticle(updated)
    },
  })

  const counts = {
    all: articles.length,
    draft: articles.filter((a) => a.status === 'draft').length,
    review: articles.filter((a) => a.status === 'review').length,
    approved: articles.filter((a) => a.status === 'approved').length,
    published: articles.filter((a) => a.status === 'published').length,
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-gray-900">Content</h1>
        <p className="text-sm text-gray-400 mt-0.5">
          AI-generated drafts awaiting review and approval
        </p>
      </div>

      {/* Status tabs */}
      <div className="flex gap-0.5 rounded-lg bg-gray-100 p-1 w-fit">
        {STATUS_TABS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            onClick={() => setStatusFilter(value)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              statusFilter === value
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {label}
            {value !== 'all' && counts[value] > 0 && (
              <span
                className={`ml-1.5 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                  statusFilter === value ? 'bg-gray-100 text-gray-700' : 'bg-gray-200 text-gray-500'
                }`}
              >
                {counts[value]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-gray-100" />
          ))}
        </div>
      ) : articles.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-sm text-gray-400">
            No{statusFilter !== 'all' ? ` ${statusFilter}` : ''} articles yet.{' '}
            <span className="text-gray-500">
              Trigger the content pipeline from Opportunities to generate drafts.
            </span>
          </p>
        </div>
      ) : (
        <div className="grid gap-3">
          {articles.map((article) => (
            <button
              key={article.id}
              type="button"
              onClick={() => setOpenArticle(article)}
              className="w-full text-left rounded-lg border border-gray-200 bg-white px-5 py-4 hover:border-indigo-200 hover:bg-indigo-50/30 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge variant={statusBadgeVariant(article.status)}>
                      {article.status}
                    </Badge>
                    {article.keyword && (
                      <span className="text-xs text-gray-400 font-mono truncate">
                        {article.keyword}
                      </span>
                    )}
                  </div>
                  <p className="text-sm font-medium text-gray-900 leading-snug line-clamp-2">
                    {article.title}
                  </p>
                </div>
                <div className="shrink-0 flex flex-col items-end gap-1.5 text-right">
                  <span className="text-xs text-gray-400">{timeAgo(article.created_at)}</span>
                  <div className="flex gap-1.5">
                    <ScorePill label="Voice" value={article.brand_voice_score} />
                    <ScorePill label="SEO" value={article.seo_score} />
                  </div>
                  {article.word_count != null && (
                    <span className="text-xs text-gray-400">
                      {article.word_count.toLocaleString()} words
                    </span>
                  )}
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Article drawer */}
      {openArticle && (
        <ArticleDrawer
          article={openArticle}
          onClose={() => setOpenArticle(null)}
          onStatusChange={(id, status) => updateMutation.mutate({ id, status })}
        />
      )}
    </div>
  )
}
