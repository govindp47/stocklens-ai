"use client";

import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { useAnalysisStore } from "@/store";

export function GlobalFailureBanner() {
  const [dismissed, setDismissed] = useState(false);
  const { status, marketData, news, errorMessage } = useAnalysisStore();

  const hasPartialData = marketData !== null || news !== null;
  const shouldShow =
    (status === "failed" || status === "timeout") && !dismissed;

  if (!shouldShow) return null;

  return (
    <div
      role="alert"
      className="w-full flex items-start justify-between gap-3 rounded-2xl border border-amber-200/70 bg-accent px-5 py-4 text-sm text-amber-900 animate-fade-in-up dark:border-amber-800/40 dark:text-accent-foreground"
    >
      <div className="flex items-start gap-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-amber-100 dark:bg-amber-900/40">
          <AlertTriangle
            className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400"
            aria-hidden="true"
          />
        </div>
        <div>
          <p className="font-medium text-amber-900 dark:text-accent-foreground leading-snug">
            {errorMessage
              ? errorMessage
              : hasPartialData
                ? "Analysis completed with errors. Some data may be incomplete or unavailable."
                : "Analysis failed. Please try again."}
          </p>
        </div>
      </div>
      <button
        onClick={() => setDismissed(true)}
        aria-label="Dismiss warning"
        className="shrink-0 flex h-7 w-7 items-center justify-center rounded-lg text-amber-600 hover:text-amber-900 hover:bg-amber-100
          focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400 transition-colors dark:hover:bg-amber-900/40"
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
