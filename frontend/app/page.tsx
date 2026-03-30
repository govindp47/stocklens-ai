'use client';

/**
 * PlaygroundPage — the main analysis page.
 *
 * Layout:
 * - Always visible: TickerInput, Settings trigger button.
 * - Pre-analysis: centered empty state hint.
 * - Post-analysis: ReasoningViewer + ReportGrid (rendered only when runId !== null).
 */

import { useAnalysisStore } from '@/store';
import { TickerInput } from '@/components/playground/TickerInput';
import { ReasoningViewer } from '@/components/playground/ReasoningViewer';
import { ReportGrid } from '@/components/playground/ReportGrid';
import { SettingsModal } from '@/components/settings/SettingsModal';

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
      {/* Top bar: ticker input + settings trigger */}
      <div className="w-full max-w-sm flex flex-col items-center gap-3">
        <div className="w-full flex items-center justify-end">
          <SettingsModal />
        </div>
        <TickerInput />
      </div>

      {/* Post-analysis layout */}
      {runId && (
        <div className="w-full max-w-5xl flex flex-col gap-4">
          <ReasoningViewer />
          <ReportGrid />
        </div>
      )}

      {/* Pre-analysis empty state */}
      {!runId && <EmptyState />}
    </div>
  );
}
