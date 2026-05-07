'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'

interface ResearchModalProps {
  open: boolean
  onClose: () => void
  onResearch: (seed: string) => Promise<void>
  isLoading: boolean
  error?: string | null
}

export function ResearchModal({
  open,
  onClose,
  onResearch,
  isLoading,
  error,
}: ResearchModalProps) {
  const router = useRouter()
  const [seed, setSeed] = useState('')

  useEffect(() => {
    if (!open) setSeed('')
  }, [open])

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleSubmit()
      if (e.key === 'Escape' && !isLoading) onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  })

  const handleSubmit = async () => {
    if (!seed.trim() || isLoading) return
    await onResearch(seed.trim())
  }

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={() => !isLoading && onClose()}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/30" />

      {/* Modal */}
      <div
        className="relative z-10 bg-white rounded-xl shadow-2xl w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Head */}
        <div className="px-5 pt-5 pb-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">
            Research keywords
          </h2>
          <p className="text-xs text-gray-500 mt-1">
            POSTs to{' '}
            <code className="font-mono bg-gray-100 px-1 rounded text-gray-600">
              /api/v1/keywords/research
            </code>
            . Returns ~10 new keywords as{' '}
            <strong className="font-medium">raw</strong>.
          </p>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">
          {/* Error / warning banner */}
          {error && !isLoading && (() => {
            const isConfigNotice =
              error.toLowerCase().includes('dataforseo') ||
              error.toLowerCase().includes('credentials') ||
              error.toLowerCase().includes('pending') ||
              error.toLowerCase().includes('402')
            return isConfigNotice ? (
              <div className="rounded-lg border border-yellow-200 bg-yellow-50 px-3 py-3 text-xs text-yellow-800 space-y-1.5">
                <div className="font-medium">DataForSEO not configured</div>
                <div className="leading-relaxed text-yellow-700">
                  Keywords will be sourced from Google Suggest. Volume, KD, and CPC will be blank
                  until you configure DataForSEO and click <strong className="font-medium">Fetch metrics</strong>.
                </div>
                <button
                  type="button"
                  onClick={() => { onClose(); router.push('/settings') }}
                  className="inline-flex items-center gap-1 text-yellow-700 underline underline-offset-2 hover:text-yellow-900"
                >
                  → Configure DataForSEO in Settings → Integrations
                </button>
              </div>
            ) : (
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-3 text-xs text-red-700 space-y-1.5">
                <div className="font-medium text-red-800">Research failed</div>
                <div className="leading-relaxed">{error}</div>
              </div>
            )
          })()}

          <div>
            <label className="block text-xs font-medium text-gray-700 mb-1.5">
              Seed keyword
            </label>
            <input
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:opacity-50 disabled:bg-gray-50"
              placeholder="e.g. ai marketing automation"
              value={seed}
              onChange={(e) => setSeed(e.target.value)}
              autoFocus
              disabled={isLoading}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            />
            <p className="text-xs text-gray-400 mt-2">
              Upload documents in{' '}
              <span className="font-medium text-gray-500">Knowledge Base</span>{' '}
              to get topic suggestions here.
            </p>
          </div>

          {/* What happens next */}
          <div className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-3 text-xs text-gray-500">
            <div className="font-medium text-gray-700 text-[13px] mb-2">
              What happens next
            </div>
            <ol className="space-y-1 list-decimal list-inside">
              <li>
                <code className="font-mono text-gray-600">keyword_research</code>{' '}
                agent expands seed → ~10 raw keywords
              </li>
              <li>
                You then run{' '}
                <code className="font-mono text-gray-600">keyword_validator</code>{' '}
                → validated or archived
              </li>
              <li>
                <code className="font-mono text-gray-600">gap_analyzer</code>{' '}
                groups validated → clusters
              </li>
            </ol>
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 pb-5 flex items-center justify-between gap-3">
          <span className="text-xs text-gray-400">
            <kbd className="font-mono bg-gray-100 px-1.5 py-0.5 rounded border border-gray-200 text-gray-500">
              ⌘ ↵
            </kbd>{' '}
            to submit
          </span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!seed.trim() || isLoading}
              className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
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
                  Run keyword_research
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
