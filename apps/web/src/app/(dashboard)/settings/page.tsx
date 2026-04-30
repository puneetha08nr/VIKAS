"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

interface SettingsState {
  openai_api_key: string;
  anthropic_api_key: string;
  wordpress_url: string;
  wordpress_app_password: string;
  gsc_service_account: string;
}

export default function SettingsPage() {
  const [form, setForm] = useState<SettingsState>({
    openai_api_key: "",
    anthropic_api_key: "",
    wordpress_url: "",
    wordpress_app_password: "",
    gsc_service_account: "",
  });
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  function handleChange(key: keyof SettingsState) {
    return (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setForm((prev) => ({ ...prev, [key]: e.target.value }));
      setSaved(false);
    };
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    // TODO: POST to /api/v1/orgs/settings
    await new Promise((r) => setTimeout(r, 500));
    setSaving(false);
    setSaved(true);
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure API keys and integrations for your organization.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* LLM Keys */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">LLM Providers</CardTitle>
            <CardDescription>Add API keys to enable real AI calls.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="openai_api_key">OpenAI API Key</Label>
              <Input
                id="openai_api_key"
                type="password"
                placeholder="sk-..."
                value={form.openai_api_key}
                onChange={handleChange("openai_api_key")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="anthropic_api_key">Anthropic API Key</Label>
              <Input
                id="anthropic_api_key"
                type="password"
                placeholder="sk-ant-..."
                value={form.anthropic_api_key}
                onChange={handleChange("anthropic_api_key")}
              />
            </div>
          </CardContent>
        </Card>

        {/* WordPress */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">WordPress</CardTitle>
            <CardDescription>Connect your WordPress site for publishing.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="wordpress_url">Site URL</Label>
              <Input
                id="wordpress_url"
                type="url"
                placeholder="https://yourblog.com"
                value={form.wordpress_url}
                onChange={handleChange("wordpress_url")}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="wordpress_app_password">Application Password</Label>
              <Input
                id="wordpress_app_password"
                type="password"
                placeholder="xxxx xxxx xxxx xxxx"
                value={form.wordpress_app_password}
                onChange={handleChange("wordpress_app_password")}
              />
            </div>
          </CardContent>
        </Card>

        {/* GSC */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Google Search Console</CardTitle>
            <CardDescription>Paste your service account JSON for GSC access.</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <Label htmlFor="gsc_service_account">Service Account JSON</Label>
              <textarea
                id="gsc_service_account"
                rows={6}
                placeholder='{"type": "service_account", ...}'
                value={form.gsc_service_account}
                onChange={handleChange("gsc_service_account")}
                className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50 font-mono"
              />
            </div>
          </CardContent>
        </Card>

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={saving}>
            {saving ? "Saving…" : "Save settings"}
          </Button>
          {saved && <p className="text-sm text-muted-foreground">Saved.</p>}
        </div>
      </form>
    </div>
  );
}
