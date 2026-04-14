"use client";

/**
 * ReportReadyCard — shown when analysis completes instead of the inline panel grid.
 * Provides a clear CTA to navigate to the full dedicated analysis page.
 */

import { useRouter } from "next/navigation";
import { CheckCircle2, ArrowRight, RotateCcw, Sparkles } from "lucide-react";
import { useAnalysisStore } from "@/store";

export function ReportReadyCard() {
  const { runId, ticker, company, completeness, reset } = useAnalysisStore();
  const router = useRouter();

  function handleViewReport() {
    if (runId) router.push(`/analysis/${runId}`);
  }

  function handleNewSearch() {
    reset();
  }

  const companyName = company?.name;

  return (
    <div className="w-full rounded-2xl border border-border bg-surface shadow-panel overflow-hidden animate-fade-in-up">
      {/* Top accent bar — brand gradient */}
      <div className="h-1 w-full bg-gradient-to-r from-brand-500 via-emerald-400 to-brand-600" />

      <div className="px-6 py-10 flex flex-col items-center text-center gap-6">
        {/* Icon cluster */}
        <div className="relative">
          <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-emerald-50 to-brand-50 border border-emerald-100 shadow-xs dark:from-emerald-950/40 dark:to-brand-50/5 dark:border-emerald-800/40">
            <CheckCircle2
              className="h-10 w-10 text-emerald-500"
              aria-hidden="true"
            />
          </div>
          {/* Sparkles badge */}
          <div className="absolute -top-1.5 -right-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-brand-500 shadow-xs">
            <Sparkles className="h-3 w-3 text-white" aria-hidden="true" />
          </div>
          {/* Subtle glow */}
          <div
            className="absolute inset-0 -z-10 rounded-3xl bg-emerald-400 opacity-10 blur-2xl"
            aria-hidden="true"
          />
        </div>

        {/* Copy */}
        <div className="space-y-1.5">
          <h2 className="text-2xl font-bold text-foreground tracking-tight">
            Analysis ready
          </h2>
          <p className="text-sm text-muted-foreground">
            {companyName ? (
              <>
                <span className="font-mono font-semibold text-brand-500">
                  {ticker}
                </span>
                {" · "}
                <span>{companyName}</span>
              </>
            ) : (
              <>
                Your{" "}
                <span className="font-mono font-semibold text-brand-500">
                  {ticker}
                </span>{" "}
                report is ready
              </>
            )}
          </p>
          {completeness && completeness !== "complete" && (
            <p className="text-xs text-muted-foreground mt-1">
              {completeness === "partial"
                ? "Some data sources were unavailable — partial report generated."
                : "Limited data available — minimal report generated."}
            </p>
          )}
        </div>

        {/* CTA buttons */}
        <div className="flex flex-col sm:flex-row gap-2.5 w-full max-w-sm">
          <button
            onClick={handleViewReport}
            className="flex-1 inline-flex items-center justify-center gap-2 h-11 rounded-xl bg-brand-500 text-sm font-semibold text-white
              hover:bg-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 transition-colors active:scale-[0.98]"
          >
            View full report
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            onClick={handleNewSearch}
            className="inline-flex items-center justify-center gap-2 h-11 rounded-xl border border-border bg-surface px-5 text-sm font-medium text-muted-foreground
              hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            New search
          </button>
        </div>
      </div>
    </div>
  );
}
