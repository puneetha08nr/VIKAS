'use client'

import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

// ── Shared helpers ────────────────────────────────────────────────────────────

function SaveRow({ saving, saved }: { saving: boolean; saved: boolean }) {
  return (
    <div className="flex items-center gap-3 pt-1">
      <Button type="submit" disabled={saving}>
        {saving ? 'Saving…' : 'Save'}
      </Button>
      {saved && <p className="text-sm text-gray-500">Saved.</p>}
    </div>
  )
}

function SectionError({ message }: { message: string }) {
  return <p className="text-xs text-red-600 mt-1">{message}</p>
}

// ── API Keys section (local state only — no API yet) ─────────────────────────

function ApiKeysSection() {
  const [form, setForm] = useState({
    openai_api_key: '',
    anthropic_api_key: '',
  })
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  function handleChange(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setForm((p) => ({ ...p, [key]: e.target.value }))
      setSaved(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    await new Promise((r) => setTimeout(r, 400))
    setSaving(false)
    setSaved(true)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">LLM Providers</CardTitle>
        <CardDescription>API keys are stored server-side as env vars — these fields are for reference only.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="openai_api_key">OpenAI API Key</Label>
            <Input id="openai_api_key" type="password" placeholder="sk-…" value={form.openai_api_key} onChange={handleChange('openai_api_key')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="anthropic_api_key">Anthropic API Key</Label>
            <Input id="anthropic_api_key" type="password" placeholder="sk-ant-…" value={form.anthropic_api_key} onChange={handleChange('anthropic_api_key')} />
          </div>
          <SaveRow saving={saving} saved={saved} />
        </form>
      </CardContent>
    </Card>
  )
}

// ── WordPress section ─────────────────────────────────────────────────────────

function WordPressSection() {
  const [form, setForm] = useState({
    wordpress_url: '',
    wordpress_app_password: '',
  })
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  function handleChange(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLInputElement>) => {
      setForm((p) => ({ ...p, [key]: e.target.value }))
      setSaved(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    await new Promise((r) => setTimeout(r, 400))
    setSaving(false)
    setSaved(true)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">WordPress</CardTitle>
        <CardDescription>Connect your site for auto-publishing approved articles.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="wordpress_url">Site URL</Label>
            <Input id="wordpress_url" type="url" placeholder="https://yourblog.com" value={form.wordpress_url} onChange={handleChange('wordpress_url')} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="wordpress_app_password">Application Password</Label>
            <Input id="wordpress_app_password" type="password" placeholder="xxxx xxxx xxxx xxxx" value={form.wordpress_app_password} onChange={handleChange('wordpress_app_password')} />
          </div>
          <SaveRow saving={saving} saved={saved} />
        </form>
      </CardContent>
    </Card>
  )
}

// ── Brand Voice section ───────────────────────────────────────────────────────

function BrandVoiceSection() {
  const queryClient = useQueryClient()

  const { data: brandVoice, isLoading } = useQuery({
    queryKey: ['brand-voice'],
    queryFn: api.brandVoice.get,
    retry: false,
  })

  const [tone, setTone] = useState('')
  const [vocabulary, setVocabulary] = useState('')
  const [bannedPhrases, setBannedPhrases] = useState('')
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (brandVoice) {
      setTone(brandVoice.tone ?? '')
      setVocabulary((brandVoice.vocabulary ?? []).join(', '))
      setBannedPhrases((brandVoice.banned_phrases ?? []).join(', '))
    }
  }, [brandVoice])

  const mutation = useMutation({
    mutationFn: () =>
      api.brandVoice.update({
        tone: tone.trim() || null,
        vocabulary: vocabulary
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        banned_phrases: bannedPhrases
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
      }),
    onSuccess: () => {
      setSaved(true)
      setSaveError(null)
      queryClient.invalidateQueries({ queryKey: ['brand-voice'] })
    },
    onError: () => setSaveError('Failed to save brand voice. Is the API running?'),
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaved(false)
    mutation.mutate()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Brand Voice</CardTitle>
        <CardDescription>Guide agents to write in your brand's style.</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-9 animate-pulse rounded bg-gray-100" />
            ))}
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="tone">Tone</Label>
              <Input
                id="tone"
                placeholder="e.g. professional, conversational, authoritative"
                value={tone}
                onChange={(e) => { setTone(e.target.value); setSaved(false) }}
              />
              <p className="text-xs text-gray-400">A short description of your brand's voice.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="vocabulary">Preferred vocabulary</Label>
              <Input
                id="vocabulary"
                placeholder="e.g. growth, ROI, data-driven, actionable"
                value={vocabulary}
                onChange={(e) => { setVocabulary(e.target.value); setSaved(false) }}
              />
              <p className="text-xs text-gray-400">Comma-separated words agents should favour.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="banned">Banned phrases</Label>
              <Input
                id="banned"
                placeholder="e.g. game-changer, synergy, leverage"
                value={bannedPhrases}
                onChange={(e) => { setBannedPhrases(e.target.value); setSaved(false) }}
              />
              <p className="text-xs text-gray-400">Comma-separated phrases to never use.</p>
            </div>
            {saveError && <SectionError message={saveError} />}
            <SaveRow saving={mutation.isPending} saved={saved} />
          </form>
        )}
      </CardContent>
    </Card>
  )
}

// ── Auto Mode section ─────────────────────────────────────────────────────────

function AutoModeSection() {
  const queryClient = useQueryClient()

  const { data: settings, isLoading } = useQuery({
    queryKey: ['auto-mode-settings'],
    queryFn: api.autoMode.get,
    retry: false,
  })

  const [enabled, setEnabled] = useState(false)
  const [scheduleTime, setScheduleTime] = useState('02:00')
  const [seedKeywords, setSeedKeywords] = useState('')
  const [maxPipelines, setMaxPipelines] = useState('5')
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    if (settings) {
      setEnabled(settings.enabled)
      setScheduleTime(settings.schedule_time ?? '02:00')
      setSeedKeywords((settings.seed_keywords ?? []).join(', '))
      setMaxPipelines(String(settings.max_daily_pipelines ?? 5))
    }
  }, [settings])

  const mutation = useMutation({
    mutationFn: () =>
      api.autoMode.update({
        enabled,
        schedule_time: scheduleTime,
        seed_keywords: seedKeywords
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        max_daily_pipelines: Math.max(1, Math.min(20, parseInt(maxPipelines) || 5)),
      }),
    onSuccess: () => {
      setSaved(true)
      setSaveError(null)
      queryClient.invalidateQueries({ queryKey: ['auto-mode-settings'] })
    },
    onError: () => setSaveError('Failed to save auto-mode settings.'),
  })

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaved(false)
    mutation.mutate()
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Auto Mode</CardTitle>
        <CardDescription>
          Runs the full pipeline nightly — research → score → content → review queue. Nothing auto-publishes.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-9 animate-pulse rounded bg-gray-100" />
            ))}
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Enable toggle */}
            <div className="flex items-center justify-between rounded-lg border border-gray-200 px-4 py-3">
              <div>
                <p className="text-sm font-medium text-gray-900">Enable Auto Mode</p>
                <p className="text-xs text-gray-400">Runs on a nightly schedule via the task queue</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={enabled}
                onClick={() => { setEnabled((v) => !v); setSaved(false) }}
                className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                  enabled ? 'bg-indigo-600' : 'bg-gray-200'
                }`}
              >
                <span
                  className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow-lg transition-transform ${
                    enabled ? 'translate-x-4' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="schedule_time">Schedule time (UTC)</Label>
              <Input
                id="schedule_time"
                type="time"
                value={scheduleTime}
                onChange={(e) => { setScheduleTime(e.target.value); setSaved(false) }}
                className="w-36"
              />
              <p className="text-xs text-gray-400">Nightly run time in UTC.</p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="seed_keywords">Seed keywords</Label>
              <Input
                id="seed_keywords"
                placeholder="e.g. ai marketing, content automation, seo tools"
                value={seedKeywords}
                onChange={(e) => { setSeedKeywords(e.target.value); setSaved(false) }}
              />
              <p className="text-xs text-gray-400">
                Comma-separated. These seed the nightly keyword research run.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="max_pipelines">Max pipelines per night</Label>
              <Input
                id="max_pipelines"
                type="number"
                min={1}
                max={20}
                value={maxPipelines}
                onChange={(e) => { setMaxPipelines(e.target.value); setSaved(false) }}
                className="w-24"
              />
              <p className="text-xs text-gray-400">
                Caps how many content pipelines run each night (1–20).
              </p>
            </div>

            {saveError && <SectionError message={saveError} />}
            <SaveRow saving={mutation.isPending} saved={saved} />
          </form>
        )}
      </CardContent>
    </Card>
  )
}

// ── GSC section ───────────────────────────────────────────────────────────────

function GscSection() {
  const [gscJson, setGscJson] = useState('')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    await new Promise((r) => setTimeout(r, 400))
    setSaving(false)
    setSaved(true)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Google Search Console</CardTitle>
        <CardDescription>Paste your service account JSON for GSC access.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="gsc_service_account">Service Account JSON</Label>
            <textarea
              id="gsc_service_account"
              rows={6}
              placeholder='{"type": "service_account", ...}'
              value={gscJson}
              onChange={(e) => { setGscJson(e.target.value); setSaved(false) }}
              className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            />
          </div>
          <SaveRow saving={saving} saved={saved} />
        </form>
      </CardContent>
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-gray-900">Settings</h1>
        <p className="mt-0.5 text-sm text-gray-400">
          Configure integrations, brand voice, and automation for your organisation.
        </p>
      </div>

      <BrandVoiceSection />
      <AutoModeSection />
      <WordPressSection />
      <ApiKeysSection />
      <GscSection />
    </div>
  )
}
