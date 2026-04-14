"use client";

/**
 * /analysis/[runId] — full dedicated analysis report page.
 * Fetches the report from the API and renders ReportDocument.
 */

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getPastResult } from "@/lib/api";
import { ReportDocument } from "@/components/analysis/ReportDocument";
import type { AnalysisReport } from "@/types/report";
import { AlertCircle, Home } from "lucide-react";
import Link from "next/link";

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function ReportSkeleton() {
  return (
    <div className="space-y-5" aria-busy="true" aria-label="Loading report">
      {/* Header skeleton — full width */}
      <div className="rounded-2xl border border-border bg-surface overflow-hidden shadow-panel">
        <div className="h-1 bg-muted animate-shimmer" />
        <div className="px-6 py-6">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-4">
              <div className="h-14 w-14 shrink-0 rounded-2xl animate-shimmer" />
              <div className="space-y-2.5 pt-1">
                <div className="h-8 w-32 rounded-lg animate-shimmer" />
                <div className="h-4 w-48 rounded-full animate-shimmer" />
                <div className="flex gap-2">
                  <div className="h-5 w-20 rounded-full animate-shimmer" />
                  <div className="h-5 w-24 rounded-full animate-shimmer" />
                </div>
              </div>
            </div>
            <div className="flex gap-2 shrink-0">
              <div className="h-9 w-20 rounded-xl animate-shimmer" />
              <div className="h-9 w-28 rounded-xl animate-shimmer" />
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: 2/3 + 1/3 grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2 rounded-2xl border border-border bg-surface shadow-panel p-5 space-y-4">
          <div className="h-5 w-32 rounded-full animate-shimmer" />
          <div className="h-16 w-40 rounded-lg animate-shimmer" />
          <div className="flex gap-px bg-border rounded-xl overflow-hidden">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="flex-1 bg-surface px-3 py-3 space-y-1.5">
                <div className="h-2 w-10 rounded animate-shimmer" />
                <div className="h-4 w-14 rounded animate-shimmer" />
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-border bg-surface shadow-panel p-5 space-y-4">
          <div className="h-5 w-28 rounded-full animate-shimmer" />
          <div className="h-10 w-24 rounded-lg animate-shimmer" />
          <div className="h-3 w-full rounded-full animate-shimmer" />
          <div className="space-y-2">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="h-3 w-20 rounded-full animate-shimmer" />
            ))}
          </div>
        </div>
      </div>

      {/* Row 3: full width chart */}
      <div className="rounded-2xl border border-border bg-surface shadow-panel p-5">
        <div className="h-5 w-28 rounded-full animate-shimmer mb-4" />
        <div className="h-72 w-full rounded-xl animate-shimmer" />
      </div>

      {/* Row 4: 1/2 + 1/2 grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {[4, 5].map((rows, i) => (
          <div
            key={i}
            className="rounded-2xl border border-border bg-surface shadow-panel p-5 space-y-3"
          >
            <div className="h-5 w-36 rounded-full animate-shimmer" />
            {[...Array(rows)].map((_, j) => (
              <div
                key={j}
                className="h-3.5 rounded-full animate-shimmer"
                style={{ width: `${[88, 72, 80, 64, 84][j % 5]}%` }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function AnalysisPage() {
  const params = useParams();
  const runId = typeof params.runId === "string" ? params.runId : "";

  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!runId) return;
    setLoading(true);
    setError(null);
    getPastResult(runId)
      .then(setReport)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load report.");
      })
      .finally(() => setLoading(false));
  }, [runId]);

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-6">
      {loading && <ReportSkeleton />}

      {!loading && error && (
        <div className="flex flex-col items-center gap-5 rounded-2xl border border-border bg-surface py-16 px-6 text-center shadow-panel">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-red-50 dark:bg-red-950/30">
            <AlertCircle className="h-7 w-7 text-red-500" aria-hidden="true" />
          </div>
          <div>
            <p className="text-base font-semibold text-foreground">
              Report not found
            </p>
            <p className="text-sm text-muted-foreground mt-1.5 max-w-xs leading-relaxed">
              {error}
            </p>
          </div>
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-semibold text-white
              hover:bg-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 transition-colors"
          >
            <Home className="h-4 w-4" aria-hidden="true" />
            Back to Analyze
          </Link>
        </div>
      )}

      {!loading && report && <ReportDocument report={report} />}

      {!loading && !report && !error && (
        <div className="flex flex-col items-center gap-4 py-16 text-muted-foreground">
          <div className="h-12 w-12 rounded-2xl animate-shimmer" />
          <span className="text-sm">Loading report…</span>
        </div>
      )}
    </div>
  );
}
