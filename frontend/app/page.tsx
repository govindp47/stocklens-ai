'use client';

/**
 * PlaygroundPage — the main analysis page.
 *
 * Layout:
 * - Pre-analysis: centered ticker input + empty state hint
 * - Post-analysis: ticker input (top), ReasoningViewer, then report panels
 *
 * The ReportGrid placeholder will be replaced in T-047/T-050 as panel
 * components are implemented.
 */

import { useAnalysisStore } from '@/store';
import { TickerInput } from '@/components/playground/TickerInput';
import { ReasoningViewer } from '@/components/playground/ReasoningViewer';

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-2 mt-12 text-center">
      <p className="text-base text-neutral-600 font-medium">
        AI-powered stock research — just enter a ticker to begin
      </p>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PlaygroundPage() {
  const { runId } = useAnalysisStore();

  return (
    <div className="flex min-h-[calc(100vh-3rem)] flex-col items-center px-4 py-8 gap-6">
      {/* Ticker input is always visible */}
      <div className="w-full max-w-sm">
        <TickerInput />
      </div>

      {/* Post-analysis layout */}
      {runId && (
        <div className="w-full max-w-3xl flex flex-col gap-4">
          <ReasoningViewer />
          {/* ReportGrid will be added in T-047–T-050 */}
        </div>
      )}

      {/* Pre-analysis empty state */}
      {!runId && <EmptyState />}
    </div>
  );
}
