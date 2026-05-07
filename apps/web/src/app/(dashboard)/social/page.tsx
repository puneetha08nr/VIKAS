'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { axiosInstance } from '@/lib/api'

type SocialStatus = 'draft' | 'approved' | 'published'

interface LinkedInPost {
  id: string
  article_id: string | null
  content: string
  hashtags: string[]
  status: SocialStatus
  created_at: string
  published_url?: string
}

interface TwitterThread {
  id: string
  article_id: string | null
  tweets: any
  tweet_count: number
  status: SocialStatus
  created_at: string
  published_url?: string
}

interface Newsletter {
  id: string
  article_id: string | null
  subject: string
  preview_text: string
  body_html: string
  status: SocialStatus
  created_at: string
  published_url?: string
}

function parseTweets(raw: any): string[] {
  if (!raw) return []
  if (Array.isArray(raw) && raw.length > 0) {
    const first = raw[0]
    if (typeof first === 'string' && first.trim().startsWith('{')) {
      try {
        const parsed = JSON.parse(first)
        if (parsed.tweets && Array.isArray(parsed.tweets)) return parsed.tweets
      } catch (_) { /* ignore */ }
    }
    if (typeof first === 'string') return raw as string[]
  }
  if (typeof raw === 'object' && raw !== null && Array.isArray(raw.tweets)) return raw.tweets
  return []
}

function parseLinkedIn(content: string): string {
  if (!content) return ''
  const trimmed = content.trim()
  if (trimmed.startsWith('{')) {
    try {
      const parsed = JSON.parse(trimmed)
      return parsed.post_text || content
    } catch (_) { /* ignore */ }
  }
  return content
}

function timeAgo(iso: string) {
  const ms = Date.now() - new Date(iso).getTime()
  const m = Math.floor(ms / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    draft: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    approved: 'bg-blue-50 text-blue-700 border-blue-200',
    published: 'bg-green-50 text-green-700 border-green-200',
  }
  return (
    <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${colors[status] ?? 'bg-gray-50 text-gray-600 border-gray-200'}`}>
      {status}
    </span>
  )
}

type Tab = 'linkedin' | 'twitter' | 'newsletter'

export default function SocialPage() {
  const [tab, setTab] = useState<Tab>('linkedin')
  const [selected, setSelected] = useState<LinkedInPost | TwitterThread | Newsletter | null>(null)
  const qc = useQueryClient()

  const { data: linkedinPosts = [] } = useQuery<LinkedInPost[]>({
    queryKey: ['linkedin-posts'],
    queryFn: () => axiosInstance.get('/api/v1/linkedin-posts?limit=50').then(r => r.data),
  })

  const { data: twitterThreads = [] } = useQuery<TwitterThread[]>({
    queryKey: ['twitter-threads'],
    queryFn: () => axiosInstance.get('/api/v1/twitter-threads?limit=50').then(r => r.data),
  })

  const { data: newsletters = [] } = useQuery<Newsletter[]>({
    queryKey: ['newsletters'],
    queryFn: () => axiosInstance.get('/api/v1/newsletters?limit=50').then(r => r.data),
  })

  const updateLinkedIn = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      axiosInstance.put(`/api/v1/linkedin-posts/${id}`, { status }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['linkedin-posts'] }); setSelected(null) },
  })

  const updateTwitter = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      axiosInstance.put(`/api/v1/twitter-threads/${id}`, { status }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['twitter-threads'] }); setSelected(null) },
  })

  const updateNewsletter = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      axiosInstance.put(`/api/v1/newsletters/${id}`, { status }).then(r => r.data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['newsletters'] }); setSelected(null) },
  })

  const handleAction = (id: string, status: string) => {
    if (tab === 'linkedin') updateLinkedIn.mutate({ id, status })
    if (tab === 'twitter') updateTwitter.mutate({ id, status })
    if (tab === 'newsletter') updateNewsletter.mutate({ id, status })
  }

  const tabs = [
    { key: 'linkedin' as Tab, label: 'LinkedIn', count: linkedinPosts.length },
    { key: 'twitter' as Tab, label: 'Twitter / X', count: twitterThreads.length },
    { key: 'newsletter' as Tab, label: 'Newsletter', count: newsletters.length },
  ]

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-gray-900">Social Content</h1>
        <p className="text-sm text-gray-500">AI-generated social drafts — review and publish</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === t.key
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {t.label}
            <span className="ml-1 rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{t.count}</span>
          </button>
        ))}
      </div>

      {/* LinkedIn */}
      {tab === 'linkedin' && (
        <div className="space-y-3">
          {linkedinPosts.length === 0 ? (
            <p className="text-sm text-gray-400 py-12 text-center">No LinkedIn posts yet.</p>
          ) : linkedinPosts.map(post => (
            <div key={post.id} onClick={() => setSelected(post)} className="cursor-pointer rounded-lg border border-gray-200 bg-white p-4 hover:border-indigo-300 transition-colors">
              <div className="flex items-center justify-between mb-2">
                <StatusBadge status={post.status} />
                <span className="text-xs text-gray-400">{timeAgo(post.created_at)}</span>
              </div>
              <p className="text-sm text-gray-700 line-clamp-3 whitespace-pre-wrap">{parseLinkedIn(post.content)}</p>
              {post.hashtags?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {post.hashtags.map((h, i) => (
                    <span key={i} className="text-xs text-indigo-500">#{h.replace('#', '')}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Twitter */}
      {tab === 'twitter' && (
        <div className="space-y-3">
          {twitterThreads.length === 0 ? (
            <p className="text-sm text-gray-400 py-12 text-center">No Twitter threads yet.</p>
          ) : twitterThreads.map(thread => {
            const tweets = parseTweets(thread.tweets)
            return (
              <div key={thread.id} onClick={() => setSelected(thread)} className="cursor-pointer rounded-lg border border-gray-200 bg-white p-4 hover:border-indigo-300 transition-colors">
                <div className="flex items-center justify-between mb-3">
                  <StatusBadge status={thread.status} />
                  <span className="text-xs text-gray-400">{tweets.length} tweets · {timeAgo(thread.created_at)}</span>
                </div>
                <div className="space-y-2">
                  {tweets.slice(0, 3).map((tweet: string, i: number) => (
                    <p key={i} className="text-sm text-gray-700 border-l-2 border-gray-200 pl-3">{tweet}</p>
                  ))}
                  {tweets.length > 3 && (
                    <p className="text-xs text-gray-400 pl-3">+{tweets.length - 3} more tweets</p>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Newsletter */}
      {tab === 'newsletter' && (
        <div className="space-y-3">
          {newsletters.length === 0 ? (
            <p className="text-sm text-gray-400 py-12 text-center">No newsletters yet.</p>
          ) : newsletters.map(nl => (
            <div key={nl.id} onClick={() => setSelected(nl)} className="cursor-pointer rounded-lg border border-gray-200 bg-white p-4 hover:border-indigo-300 transition-colors">
              <div className="flex items-center justify-between mb-2">
                <StatusBadge status={nl.status} />
                <span className="text-xs text-gray-400">{timeAgo(nl.created_at)}</span>
              </div>
              <p className="font-medium text-sm text-gray-900">{nl.subject || '(no subject)'}</p>
              {nl.preview_text && <p className="text-xs text-gray-500 mt-1">{nl.preview_text}</p>}
            </div>
          ))}
        </div>
      )}

      {/* Detail Drawer */}
      {selected && (
        <div className="fixed inset-0 z-40 flex">
          <div className="flex-1 bg-black/20" onClick={() => setSelected(null)} />
          <div className="w-full max-w-2xl bg-white shadow-xl flex flex-col overflow-hidden">

            {/* Header */}
            <div className="flex items-center justify-between border-b px-6 py-4">
              <div>
                <p className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                  {tab === 'linkedin' ? 'LinkedIn Post' : tab === 'twitter' ? 'Twitter Thread' : 'Newsletter'}
                </p>
                {'subject' in selected && (
                  <h2 className="mt-0.5 text-base font-semibold">{(selected as Newsletter).subject}</h2>
                )}
              </div>
              <button onClick={() => setSelected(null)} className="text-gray-400 hover:text-gray-600">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 6 6 18M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Meta */}
            <div className="flex items-center gap-3 px-6 py-3 border-b bg-gray-50">
              <StatusBadge status={selected.status} />
              <span className="text-xs text-gray-400 ml-auto">{timeAgo(selected.created_at)}</span>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto px-6 py-5">
              {tab === 'linkedin' && (
                <div>
                  <pre className="whitespace-pre-wrap text-sm text-gray-700 font-sans">
                    {parseLinkedIn((selected as LinkedInPost).content)}
                  </pre>
                  {(selected as LinkedInPost).hashtags?.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {(selected as LinkedInPost).hashtags.map((h, i) => (
                        <span key={i} className="text-sm text-indigo-600">#{h.replace('#', '')}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {tab === 'twitter' && (
                <div className="space-y-4">
                  {parseTweets((selected as TwitterThread).tweets).map((tweet: string, i: number) => (
                    <div key={i} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                      <p className="text-xs text-gray-400 mb-1">Tweet {i + 1}</p>
                      <p className="text-sm text-gray-700">{tweet}</p>
                      <p className="text-xs text-gray-400 mt-1 text-right">{tweet.length}/280</p>
                    </div>
                  ))}
                </div>
              )}

              {tab === 'newsletter' && (
                <div>
                  <div className="mb-4 p-3 rounded bg-gray-50 border text-sm">
                    <p><span className="font-medium">Subject:</span> {(selected as Newsletter).subject}</p>
                    {(selected as Newsletter).preview_text && (
                      <p className="text-gray-500 mt-1">
                        <span className="font-medium">Preview:</span> {(selected as Newsletter).preview_text}
                      </p>
                    )}
                  </div>
                  {(selected as Newsletter).body_html ? (
                    <div
                      className="prose prose-sm max-w-none text-gray-700"
                      dangerouslySetInnerHTML={{ __html: (selected as Newsletter).body_html }}
                    />
                  ) : (
                    <p className="text-sm text-gray-400 italic">No body content.</p>
                  )}
                </div>
              )}
            </div>

            {/* Mock notice */}
            <div className="mx-6 mb-2 rounded bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-700">
              Mock mode — add real API credentials in Settings to enable live publishing.
            </div>

            {/* Actions */}
            {selected.status !== 'published' && (
              <div className="border-t px-6 py-4 flex gap-3 justify-end">
                {selected.status === 'draft' && (
                  <button
                    onClick={() => handleAction(selected.id, 'approved')}
                    className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Approve
                  </button>
                )}
                <button
                  onClick={() => handleAction(selected.id, 'published')}
                  className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
                >
                  {tab === 'linkedin' ? 'Publish to LinkedIn' : tab === 'twitter' ? 'Post Thread' : 'Send Newsletter'}
                </button>
              </div>
            )}
            {selected.status === 'published' && (
              <div className="border-t px-6 py-4 text-sm text-green-600 font-medium">
                Published (mock) — add real credentials in Settings to go live.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
