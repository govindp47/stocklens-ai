'use client';

/**
 * ReasoningViewer — live display of pipeline step progress.
 *
 * Accessibility:
 * - aria-live="polite" announces new steps to screen readers without interrupting.
 * - Each step entry has an aria-label combining step name and status.
 * - Status icons are aria-hidden; the label text conveys the same info.
 */

import { CheckCircle2, XCircle, Loader2, SkipForward } from 'lucide-react';
import { useAnalysisStore, useUIStore } from '@/store';
import type { StepEvent, StepStatus } from '@/types/pipeline';

// ─── Step description lookup (mirrors backend step class names) ───────────────

const STEP_DESCRIPTIONS: Record<string, string> = {
  ticker_validation: 'Validating ticker and resolving company information',
  market_data_collection: 'Fetching current price, volume, and financial ratios',
  news_retrieval: 'Retrieving recent news articles',
  news_deduplication: 'Removing duplicate articles covering the same events',
  article_summarization: 'Summarizing each article using AI',
  sentiment_classification: 'Classifying the sentiment of each article',
  event_extraction: 'Identifying key business events from the news',
  insight_generation: 'Generating AI research overview',
  report_assembly: 'Assembling the final report',
};

// ─── Step status icon ─────────────────────────────────────────────────────────

function StepStatusIcon({ status }: { status: StepStatus }) {
  switch (status) {
    case 'completed':
      return (
        <CheckCircle2
          className="w-3.5 h-3.5 text-sentiment-positive shrink-0 mt-0.5"
          aria-hidden="true"
        />
      );
    case 'failed':
      return (
        <XCircle
          className="w-3.5 h-3.5 text-sentiment-negative shrink-0 mt-0.5"
          aria-hidden="true"
        />
      );
    case 'skipped':
      return (
        <SkipForward
          className="w-3.5 h-3.5 text-neutral-400 shrink-0 mt-0.5"
          aria-hidden="true"
        />
      );
    case 'started':
    default:
      return (
        <Loader2
          className="w-3.5 h-3.5 text-neutral-400 animate-spin shrink-0 mt-0.5"
          aria-hidden="true"
        />
      );
  }
}

// ─── Single step entry ────────────────────────────────────────────────────────

function StepEntry({
  event,
  animationDelay,
}: {
  event: StepEvent;
  animationDelay: number;
}) {
  const description = STEP_DESCRIPTIONS[event.step] ?? event.step;
  const statusLabel =
    event.status.charAt(0).toUpperCase() + event.status.slice(1);

  return (
    <li
      className="flex items-start gap-2 text-xs"
      style={{ animationDelay: `${animationDelay}ms` }}
      aria-label={`${description} — ${statusLabel}`}
    >
      <StepStatusIcon status={event.status} />
      <span className="font-medium text-neutral-700">{description}</span>
    </li>
  );
}

// ─── Pending indicator shown while streaming ─────────────────────────────────

function StepEntryPending() {
  return (
    <li className="flex items-center gap-2 text-xs text-neutral-400" aria-hidden="true">
      <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
      <span>Running next step…</span>
    </li>
  );
}

// ─── ReasoningViewer ─────────────────────────────────────────────────────────

export function ReasoningViewer() {
  const { stepEvents, status } = useAnalysisStore();
  const { reasoningViewerExpanded, toggleReasoningViewer } = useUIStore();

  return (
    <section
      aria-label="Analysis reasoning steps"
      aria-live="polite"
      className="mb-4 rounded-lg border border-neutral-200 bg-neutral-50 px-4 py-3"
    >
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-neutral-700">
          Agent Reasoning
        </h2>
        <button
          onClick={toggleReasoningViewer}
          aria-expanded={reasoningViewerExpanded}
          aria-controls="reasoning-viewer-list"
          className="text-xs text-neutral-400 hover:text-neutral-600 min-h-[44px] px-2 focus:outline-none focus:ring-2 focus:ring-brand-500 rounded"
        >
          {reasoningViewerExpanded ? 'Collapse' : 'Expand'}
        </button>
      </div>

      {reasoningViewerExpanded && (
        <ol
          id="reasoning-viewer-list"
          className="space-y-1.5"
        >
          {stepEvents.map((event, index) => (
            <StepEntry
              key={`${event.step}-${index}`}
              event={event}
              animationDelay={index * 50}
            />
          ))}
          {(status === 'streaming' || status === 'loading') && (
            <StepEntryPending />
          )}
        </ol>
      )}
    </section>
  );
}
