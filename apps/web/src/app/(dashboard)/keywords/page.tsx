"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  getAgentRun,
  getKeywords,
  getKeywordStats,
  runKeywordResearch,
  type KeywordRow,
} from "@/lib/api";

const intentStyles: Record<string, string> = {
  commercial: "bg-green-100 text-green-800",
  informational: "bg-blue-100 text-blue-800",
  transactional: "bg-orange-100 text-orange-800",
  navigational: "bg-gray-100 text-gray-700",
};

function IntentBadge({ intent }: { intent: string | null }) {
  if (!intent) return <span className="text-muted-foreground">—</span>;
  const cls = intentStyles[intent] ?? "bg-gray-100 text-gray-700";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      {intent}
    </span>
  );
}

function KdCell({ kd }: { kd: number | null }) {
  if (kd == null) return <span className="text-muted-foreground">—</span>;
  const cls =
    kd <= 4 ? "text-green-700" : kd <= 7 ? "text-orange-600" : "text-red-600";
  return <span className={`font-medium tabular-nums ${cls}`}>{kd.toFixed(1)}</span>;
}

export default function KeywordsPage() {
  const [seed, setSeed] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const queryClient = useQueryClient();

  const { data: keywords = [], isLoading: keywordsLoading } = useQuery({
    queryKey: ["keywords"],
    queryFn: () => getKeywords(),
  });

  const { data: stats } = useQuery({
    queryKey: ["keyword-stats"],
    queryFn: getKeywordStats,
  });

  const { data: runStatus } = useQuery({
    queryKey: ["agent-run", runId],
    queryFn: () => getAgentRun(runId!),
    enabled: !!runId,
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 3000 : false,
  });

  useEffect(() => {
    if (
      runStatus?.status === "success" ||
      runStatus?.status === "failed"
    ) {
      queryClient.invalidateQueries({ queryKey: ["keywords"] });
      queryClient.invalidateQueries({ queryKey: ["keyword-stats"] });
      setRunId(null);
    }
  }, [runStatus?.status, queryClient]);

  async function handleResearch() {
    if (!seed.trim()) return;
    setIsSubmitting(true);
    try {
      const { run_id } = await runKeywordResearch(seed.trim());
      setRunId(run_id);
      setSeed("");
    } finally {
      setIsSubmitting(false);
    }
  }

  const isRunning = runStatus?.status === "running";
  const busy = isSubmitting || isRunning;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Keywords</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Research and manage your SEO keyword library.
        </p>
      </div>

      {/* Research input */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Keyword Research</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-3">
            <div className="flex-1">
              <Label htmlFor="seed" className="sr-only">
                Seed keyword
              </Label>
              <Input
                id="seed"
                placeholder="Enter a seed keyword (e.g. ai marketing)"
                value={seed}
                onChange={(e) => setSeed(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleResearch()}
                disabled={busy}
              />
            </div>
            <Button onClick={handleResearch} disabled={!seed.trim() || busy}>
              {busy ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {isRunning ? "Researching…" : "Starting…"}
                </>
              ) : (
                <>
                  <Search className="mr-2 h-4 w-4" />
                  Research
                </>
              )}
            </Button>
          </div>
          {runStatus?.status === "failed" && (
            <p className="mt-2 text-sm text-red-600">
              Research failed: {runStatus.error ?? "unknown error"}
            </p>
          )}
        </CardContent>
      </Card>

      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          {(
            [
              { label: "Total", value: stats.total },
              { label: "Raw", value: stats.raw },
              { label: "Validated", value: stats.validated },
              { label: "Commercial", value: stats.commercial },
              { label: "Informational", value: stats.informational },
            ] as const
          ).map(({ label, value }) => (
            <Card key={label}>
              <CardContent className="pt-4 pb-3">
                <p className="text-2xl font-bold">{value}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Keywords table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Keyword Library
            {keywords.length > 0 && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({keywords.length})
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {keywordsLoading ? (
            <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Loading keywords…
            </div>
          ) : keywords.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No keywords yet. Run a research job to get started.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50">
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                      Keyword
                    </th>
                    <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                      Volume
                    </th>
                    <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                      KD
                    </th>
                    <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                      CPC
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                      Intent
                    </th>
                    <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                      Status
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {keywords.map((kw: KeywordRow) => (
                    <tr
                      key={kw.id}
                      className="border-b last:border-0 hover:bg-muted/30 transition-colors"
                    >
                      <td className="px-4 py-3 font-medium">{kw.keyword}</td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {kw.volume != null ? kw.volume.toLocaleString() : "—"}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <KdCell kd={kw.kd} />
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">
                        {kw.cpc != null ? `$${kw.cpc.toFixed(2)}` : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <IntentBadge intent={kw.intent} />
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-xs capitalize text-muted-foreground">
                          {kw.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
