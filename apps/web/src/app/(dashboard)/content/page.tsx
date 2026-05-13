'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, axiosInstance } from '@/lib/api'
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
  const [activeTab, setActiveTab] = useState<'plan' | 'article'>('article')

  const planId = (article as any).article_plan_id
  const qc = useQueryClient()

  const { data: plan } = useQuery({
    queryKey: ['article-plan', planId],
    queryFn: () => axiosInstance.get(`/api/v1/article-plans/${planId}`).then(r => r.data),
    enabled: activeTab === 'plan' && !!planId,
  })

  const [editingSections, setEditingSections] = useState<any[]>([])
  const [editingTitle, setEditingTitle] = useState('')
  const [editingCta, setEditingCta] = useState('')
  const [isEditing, setIsEditing] = useState(false)
  const [saving, setSaving] = useState(false)

  const startEditing = () => {
    setEditingSections(JSON.parse(JSON.stringify(plan?.outline || [])))
    setEditingTitle(plan?.title || '')
    setEditingCta(plan?.cta || '')
    setIsEditing(true)
  }

  const cancelEditing = () => {
    setIsEditing(false)
    setEditingSections([])
  }

  const saveOutline = async () => {
    setSaving(true)
    try {
      await axiosInstance.put(`/api/v1/article-plans/${planId}`, {
        outline: editingSections,
        title: editingTitle,
        cta: editingCta,
      })
      qc.invalidateQueries({ queryKey: ['article-plan', planId] })
      setIsEditing(false)
    } catch (_) { /* ignore */ } finally { setSaving(false) }
  }

  const approvePlan = async () => {
    setSaving(true)
    try {
      // 1. Mark plan as approved
      await axiosInstance.put(`/api/v1/article-plans/${planId}`, { status: 'approved' })
      qc.invalidateQueries({ queryKey: ['article-plan', planId] })

      // 2. Trigger article_writer with the approved plan
      await axiosInstance.post('/api/v1/agents/article_writer/run', {
        params: { article_plan_id: planId },
      })

      // 3. Refresh articles list
      qc.invalidateQueries({ queryKey: ['articles'] })

      alert('✅ Outline approved! Article writer is running — check Content page in ~5 minutes.')
    } catch (err) {
      alert('Failed to trigger article writer. Check that the API is running.')
    } finally {
      setSaving(false)
    }
  }

  const updateSection = (i: number, field: string, value: string) => {
    setEditingSections(prev => prev.map((s, idx) =>
      idx === i ? { ...s, [field]: value } : s
    ))
  }

  const deleteSection = (i: number) => {
    setEditingSections(prev => prev.filter((_, idx) => idx !== i))
  }

  const addSection = () => {
    setEditingSections(prev => [...prev, { h2: 'New Section', detail: '', h3s: [] }])
  }

  const moveSection = (i: number, dir: -1 | 1) => {
    const arr = [...editingSections]
    const j = i + dir
    if (j < 0 || j >= arr.length) return
    ;[arr[i], arr[j]] = [arr[j], arr[i]]
    setEditingSections(arr)
  }

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
      <div className="flex-1 bg-black/20" onClick={onClose} aria-hidden="true" />
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
          <button type="button" onClick={onClose} className="ml-4 shrink-0 text-gray-400 hover:text-gray-600">
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

        {/* Tabs */}
        <div className="flex border-b border-gray-200 px-6">
          {(['plan', 'article'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`py-2.5 px-4 text-sm font-medium border-b-2 transition-colors capitalize ${
                activeTab === tab
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab === 'plan' ? '📋 Outline' : '📄 Article'}
            </button>
          ))}
        </div>

        {/* Plan tab */}
        {activeTab === 'plan' && (
          <div className="flex-1 overflow-y-auto px-6 py-5">
            {plan ? (
              <div className="space-y-4">

                {/* Status + action bar */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      plan.status === 'approved' ? 'bg-green-100 text-green-700' :
                      plan.status === 'written' ? 'bg-blue-100 text-blue-700' :
                      'bg-yellow-100 text-yellow-700'
                    }`}>{plan.status}</span>
                    <span className="text-xs text-gray-400">{plan.word_count_target} words target</span>
                  </div>
                  <div className="flex gap-2">
                    {!isEditing && (
                      <>
                        <button onClick={startEditing}
                          className="text-xs px-3 py-1.5 border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50">
                          ✏️ Edit
                        </button>
                        {plan.status !== 'approved' && (
                          <button onClick={approvePlan} disabled={saving}
                            className="text-xs px-3 py-1.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50">
                            ✓ Approve Outline
                          </button>
                        )}
                      </>
                    )}
                    {isEditing && (
                      <>
                        <button onClick={cancelEditing}
                          className="text-xs px-3 py-1.5 border border-gray-300 rounded-lg text-gray-600 hover:bg-gray-50">
                          Cancel
                        </button>
                        <button onClick={saveOutline} disabled={saving}
                          className="text-xs px-3 py-1.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50">
                          {saving ? 'Saving...' : '💾 Save'}
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Title */}
                <div className="bg-indigo-50 rounded-lg p-3 border border-indigo-100">
                  <p className="text-xs font-medium text-indigo-500 uppercase mb-1">Title</p>
                  {isEditing ? (
                    <input value={editingTitle} onChange={e => setEditingTitle(e.target.value)}
                      className="w-full text-sm font-semibold text-gray-900 bg-white border border-indigo-200 rounded px-2 py-1 outline-none focus:border-indigo-400" />
                  ) : (
                    <p className="text-sm font-semibold text-gray-900">{plan.title}</p>
                  )}
                </div>

                {/* Content angle */}
                {plan.content_angle && (
                  <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                    <p className="text-xs font-medium text-gray-400 uppercase mb-1">Content Angle</p>
                    <p className="text-sm text-gray-700">{plan.content_angle}</p>
                  </div>
                )}

                {/* Sections */}
                <div>
                  <p className="text-xs font-medium text-gray-400 uppercase mb-2">Sections</p>
                  <div className="space-y-2">
                    {(isEditing ? editingSections : plan.outline || []).map((section: any, i: number) => (
                      <div key={i} className="rounded-lg border border-gray-200 bg-white p-3">
                        {isEditing ? (
                          <div className="space-y-2">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-bold text-indigo-500 shrink-0">H2</span>
                              <input value={section.h2}
                                onChange={e => updateSection(i, 'h2', e.target.value)}
                                className="flex-1 text-sm font-semibold border border-gray-200 rounded px-2 py-1 outline-none focus:border-indigo-400" />
                              <button onClick={() => moveSection(i, -1)} className="text-gray-400 hover:text-gray-600 text-xs">↑</button>
                              <button onClick={() => moveSection(i, 1)} className="text-gray-400 hover:text-gray-600 text-xs">↓</button>
                              <button onClick={() => deleteSection(i)} className="text-red-400 hover:text-red-600 text-xs">✕</button>
                            </div>
                            <textarea value={section.detail}
                              onChange={e => updateSection(i, 'detail', e.target.value)}
                              rows={2}
                              placeholder="What to cover in this section..."
                              className="w-full text-xs text-gray-600 border border-gray-200 rounded px-2 py-1 outline-none focus:border-indigo-400 resize-none ml-7" />
                          </div>
                        ) : (
                          <>
                            <div className="flex items-center gap-2 mb-1">
                              <span className="text-xs font-bold text-indigo-500">H2</span>
                              <p className="text-sm font-semibold text-gray-900">{section.h2}</p>
                            </div>
                            {section.detail && (
                              <p className="text-xs text-gray-500 ml-7">{section.detail}</p>
                            )}
                            {section.h3s?.length > 0 && (
                              <div className="ml-7 mt-1 space-y-0.5">
                                {section.h3s.map((h3: string, j: number) => (
                                  <div key={j} className="flex items-center gap-1.5">
                                    <span className="text-xs text-gray-400">H3</span>
                                    <p className="text-xs text-gray-600">{h3}</p>
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                  {isEditing && (
                    <button onClick={addSection}
                      className="mt-2 w-full text-xs text-indigo-600 border border-dashed border-indigo-300 rounded-lg py-2 hover:bg-indigo-50 transition-colors">
                      + Add Section
                    </button>
                  )}
                </div>

                {/* CTA */}
                <div className="bg-green-50 rounded-lg p-3 border border-green-100">
                  <p className="text-xs font-medium text-green-500 uppercase mb-1">
                    CTA — Call To Action (final line of article)
                  </p>
                  {isEditing ? (
                    <input value={editingCta} onChange={e => setEditingCta(e.target.value)}
                      className="w-full text-sm text-gray-700 bg-white border border-green-200 rounded px-2 py-1 outline-none focus:border-green-400" />
                  ) : (
                    <p className="text-sm text-gray-700">{plan.cta || 'No CTA set'}</p>
                  )}
                </div>

              </div>
            ) : !planId ? (
              <p className="text-sm text-gray-400 italic text-center py-8">
                No outline available — this article was written without a plan.
              </p>
            ) : (
              <p className="text-sm text-gray-400 italic text-center py-8">Loading outline...</p>
            )}
          </div>
        )}

        {/* Article tab */}
        {activeTab === 'article' && (
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
        )}

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
            <div className="ml-auto flex gap-2">
              {/* Reject button */}
              {article.status === 'review' && (
                <button
                  type="button"
                  onClick={async () => {
                    const reason = prompt('Why are you rejecting this? (optional)')
                    await axiosInstance.post('/api/v1/content-feedback', {
                      content_type: 'article',
                      content_id: article.id,
                      action: 'rejected',
                      notes: reason || '',
                    })
                    onStatusChange(article.id, 'draft')
                  }}
                  className="inline-flex items-center rounded-md border border-red-300 px-3.5 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
                >
                  Reject
                </button>
              )}
              {/* Approve button */}
              <button
                type="button"
                onClick={async () => {
                  const next = nextStatus[article.status]
                  if (!next) return
                  // Record feedback
                  const action = article.status === 'review' ? 'approved' : 'approved'
                  await axiosInstance.post('/api/v1/content-feedback', {
                    content_type: 'article',
                    content_id: article.id,
                    action,
                    notes: '',
                  }).catch(() => {/* ignore */})
                  onStatusChange(article.id, next)
                }}
                className="inline-flex items-center rounded-md bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-indigo-700"
              >
                {actionLabel[article.status]}
              </button>
            </div>
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
