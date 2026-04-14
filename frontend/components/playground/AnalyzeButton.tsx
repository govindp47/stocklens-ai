"use client";

/**
 * AnalyzeButton — submit button for the ticker analysis form.
 *
 * - Disabled during 'loading' and 'streaming' states.
 * - Shows a spinner icon (with screen-reader text) while running.
 * - Shows "New search" with outlined style after completion/failure.
 * - Meets 44px minimum touch target.
 */

import { Loader2, Search, RefreshCw } from "lucide-react";

type AnalysisStatus =
  | "idle"
  | "loading"
  | "streaming"
  | "complete"
  | "failed"
  | "timeout";

interface AnalyzeButtonProps {
  status: AnalysisStatus;
}

export function AnalyzeButton({ status }: AnalyzeButtonProps) {
  const isRunning = status === "loading" || status === "streaming";
  const isDone = status === "complete" || status === "failed";

  return (
    <>
      <span className="sr-only" aria-live="polite" aria-atomic="true">
        {isRunning ? "Analysis in progress" : ""}
      </span>
      <button
        type="submit"
        disabled={isRunning}
        aria-disabled={isRunning}
        className={`inline-flex h-11 min-w-[108px] items-center justify-center gap-2 rounded-xl px-5 text-sm font-semibold
          transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-1
          ${
            isRunning
              ? "bg-brand-500 text-white opacity-70 cursor-not-allowed"
              : isDone
                ? "border border-border bg-surface text-foreground hover:border-brand-200 hover:text-brand-600 hover:bg-brand-50"
                : "bg-brand-500 text-white shadow-xs hover:bg-brand-600 active:scale-[0.98]"
          }`}
      >
        {isRunning ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            <span>Analyzing</span>
          </>
        ) : isDone ? (
          <>
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            <span>New search</span>
          </>
        ) : (
          <>
            <Search className="h-4 w-4" aria-hidden="true" />
            <span>Analyze</span>
          </>
        )}
      </button>
    </>
  );
}
