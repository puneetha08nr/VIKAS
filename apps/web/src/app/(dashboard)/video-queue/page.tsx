'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Badge, statusBadgeVariant } from '@/components/ui/badge'
import type { VideoJob, VideoJobStatus } from '@/lib/types'

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime()
  const minutes = Math.floor(ms / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return '—'
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return m > 0 ? `${m}m ${s}s` : `${s}s`
}

const STATUS_FILTERS: { value: VideoJobStatus | 'all'; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'pending_video', label: 'Pending' },
  { value: 'video_ready', label: 'Ready' },
  { value: 'published', label: 'Published' },
  { value: 'failed', label: 'Failed' },
]

const STATUS_ICON: Record<VideoJobStatus, React.ReactNode> = {
  pending_video: (
    <svg className="text-amber-400" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  ),
  video_ready: (
    <svg className="text-green-500" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  ),
  published: (
    <svg className="text-indigo-500" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
      <polyline points="22 4 12 14.01 9 11.01" />
    </svg>
  ),
  failed: (
    <svg className="text-red-400" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="15" y1="9" x2="9" y2="15" />
      <line x1="9" y1="9" x2="15" y2="15" />
    </svg>
  ),
}

function VideoJobCard({
  job,
  onStatusChange,
  updating,
}: {
  job: VideoJob
  onStatusChange: (id: string, status: VideoJobStatus) => void
  updating: boolean
}) {
  const nextStatus: Partial<Record<VideoJobStatus, VideoJobStatus>> = {
    pending_video: 'video_ready',
    video_ready: 'published',
  }
  const actionLabel: Partial<Record<VideoJobStatus, string>> = {
    pending_video: 'Mark Ready',
    video_ready: 'Mark Published',
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white px-5 py-4 hover:border-gray-300 transition-colors">
      <div className="flex items-start gap-3">
        {/* Status icon */}
        <div className="mt-0.5 shrink-0">
          {STATUS_ICON[job.status]}
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 leading-snug line-clamp-2">
                {job.title ?? '(untitled script)'}
              </p>
              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                <Badge variant={statusBadgeVariant(job.status)}>{job.status.replace('_', ' ')}</Badge>
                {job.scene_count != null && (
                  <span className="text-xs text-gray-400">
                    {job.scene_count} scene{job.scene_count !== 1 ? 's' : ''}
                  </span>
                )}
                {job.duration_seconds != null && (
                  <span className="text-xs text-gray-400">
                    {formatDuration(job.duration_seconds)}
                  </span>
                )}
                <span className="text-xs text-gray-400 ml-auto">{timeAgo(job.created_at)}</span>
              </div>
              {job.notes && (
                <p className="mt-1.5 text-xs text-gray-500 line-clamp-1">{job.notes}</p>
              )}
            </div>

            {/* Actions */}
            <div className="shrink-0 flex flex-col items-end gap-2">
              {job.video_url && (
                <a
                  href={job.video_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:border-indigo-300 hover:text-indigo-600 transition-colors"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                    <polygon points="5 3 19 12 5 21 5 3" />
                  </svg>
                  Watch
                </a>
              )}
              {job.upload_url && !job.video_url && (
                <a
                  href={job.upload_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:border-indigo-300 hover:text-indigo-600 transition-colors"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                    <polyline points="17 8 12 3 7 8" />
                    <line x1="12" y1="3" x2="12" y2="15" />
                  </svg>
                  Upload
                </a>
              )}
              {nextStatus[job.status] && (
                <button
                  type="button"
                  disabled={updating}
                  onClick={() => {
                    const next = nextStatus[job.status]
                    if (next) onStatusChange(job.id, next)
                  }}
                  className="inline-flex items-center gap-1 rounded-md bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {updating ? (
                    <svg className="animate-spin h-3 w-3" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
                    </svg>
                  ) : null}
                  {actionLabel[job.status]}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function VideoQueuePage() {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<VideoJobStatus | 'all'>('all')
  const [updatingId, setUpdatingId] = useState<string | null>(null)

  const { data: allJobs = [], isLoading } = useQuery({
    queryKey: ['video-jobs'],
    queryFn: () => api.videoJobs.list(),
    retry: false,
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: VideoJobStatus }) =>
      api.videoJobs.update(id, { status }),
    onMutate: ({ id }) => setUpdatingId(id),
    onSettled: () => {
      setUpdatingId(null)
      queryClient.invalidateQueries({ queryKey: ['video-jobs'] })
    },
  })

  const filtered =
    statusFilter === 'all'
      ? allJobs
      : allJobs.filter((j) => j.status === statusFilter)

  const counts: Record<string, number> = {
    all: allJobs.length,
    pending_video: allJobs.filter((j) => j.status === 'pending_video').length,
    video_ready: allJobs.filter((j) => j.status === 'video_ready').length,
    published: allJobs.filter((j) => j.status === 'published').length,
    failed: allJobs.filter((j) => j.status === 'failed').length,
  }

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-gray-900">Video Queue</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            Scripts ready for video production
          </p>
        </div>
        {counts.pending_video > 0 && (
          <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-700">
            {counts.pending_video} pending
          </span>
        )}
      </div>

      {/* Filter pills */}
      <div className="flex flex-wrap gap-1.5">
        {STATUS_FILTERS.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            onClick={() => setStatusFilter(value)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              statusFilter === value
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
          >
            {label}
            {counts[value] > 0 && (
              <span className={`ml-1.5 ${statusFilter === value ? 'opacity-75' : 'text-gray-400'}`}>
                {counts[value]}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Jobs */}
      {isLoading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-lg bg-gray-100" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="py-16 text-center">
          <svg
            className="mx-auto mb-3 text-gray-300"
            width="40"
            height="40"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" />
            <line x1="7" y1="2" x2="7" y2="22" />
            <line x1="17" y1="2" x2="17" y2="22" />
            <line x1="2" y1="12" x2="22" y2="12" />
            <line x1="2" y1="7" x2="7" y2="7" />
            <line x1="2" y1="17" x2="7" y2="17" />
            <line x1="17" y1="17" x2="22" y2="17" />
            <line x1="17" y1="7" x2="22" y2="7" />
          </svg>
          <p className="text-sm text-gray-400">
            {statusFilter !== 'all'
              ? `No ${statusFilter.replace('_', ' ')} jobs.`
              : 'No video jobs yet. Run the video scriptwriter agent to generate scripts.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((job) => (
            <VideoJobCard
              key={job.id}
              job={job}
              updating={updatingId === job.id}
              onStatusChange={(id, status) => updateMutation.mutate({ id, status })}
            />
          ))}
        </div>
      )}
    </div>
  )
}
