'use client';

/**
 * AnalyzeButton — submit button for the ticker analysis form.
 *
 * - Disabled during 'loading' and 'streaming' states.
 * - Shows a spinner icon (with screen-reader text) while running.
 * - Meets 44px minimum touch target.
 */

import { Loader2, Search } from 'lucide-react';

type AnalysisStatus = 'idle' | 'loading' | 'streaming' | 'complete' | 'failed' | 'timeout';

interface AnalyzeButtonProps {
  status: AnalysisStatus;
}

export function AnalyzeButton({ status }: AnalyzeButtonProps) {
  const isRunning = status === 'loading' || status === 'streaming';

  return (
    <button
      type="submit"
      disabled={isRunning}
      aria-disabled={isRunning}
      className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center gap-2 rounded-md bg-brand-500 px-6 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-900 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
    >
      {isRunning ? (
        <>
          <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
          <span>Analyzing…</span>
          {/* Hidden live status for screen readers */}
          <span className="sr-only" aria-live="polite">
            Analysis in progress
          </span>
        </>
      ) : (
        <>
          <Search className="w-4 h-4" aria-hidden="true" />
          <span>Analyze</span>
        </>
      )}
    </button>
  );
}
