'use client';

/**
 * SentimentPanel — sentiment distribution bar and dominant label.
 *
 * Accessibility:
 * - Each bar segment has aria-label communicating the percentage textually.
 * - Color alone is never the sole indicator — segment labels are always visible.
 * - SentimentBadge also uses icon + text, not color alone.
 * - limited_data_caveat is surfaced as a visible notice.
 */

import { useAnalysisStore } from '@/store';
import { Panel } from '@/components/ui/Panel';
import { PanelSkeleton } from '@/components/ui/PanelSkeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { SentimentBadge } from '@/components/ui/SentimentBadge';
import type { SentimentDistribution } from '@/types/report';

// ─── Sentiment bar ────────────────────────────────────────────────────────────

function SentimentBar({ distribution }: { distribution: SentimentDistribution }) {
  const { positive, neutral, negative } = distribution;

  // Segments — render even zero-width segments so aria data is always present
  const segments: Array<{
    key: string;
    pct: number;
    bg: string;
    label: string;
  }> = [
    { key: 'positive', pct: positive, bg: 'bg-sentiment-positive', label: 'Positive' },
    { key: 'neutral',  pct: neutral,  bg: 'bg-sentiment-neutral',  label: 'Neutral'  },
    { key: 'negative', pct: negative, bg: 'bg-sentiment-negative', label: 'Negative' },
  ];

  return (
    <div>
      {/* Segmented horizontal bar */}
      <div
        className="flex h-6 w-full rounded overflow-hidden"
        role="img"
        aria-label={`Sentiment distribution: Positive ${positive}%, Neutral ${neutral}%, Negative ${negative}%`}
      >
        {segments.map(({ key, pct, bg, label }) =>
          pct > 0 ? (
            <div
              key={key}
              className={`${bg} flex items-center justify-center`}
              style={{ width: `${pct}%` }}
              aria-label={`${label}: ${pct}%`}
            >
              {/* Always-visible text label inside each segment */}
              {pct >= 10 && (
                <span className="text-white text-xs font-medium select-none">
                  {pct}%
                </span>
              )}
            </div>
          ) : null
        )}
      </div>

      {/* Legend rows — percentage labels always visible below bar */}
      <div className="flex justify-between mt-2">
        {segments.map(({ key, pct, label }) => (
          <div key={key} className="flex items-center gap-1">
            <span className="text-xs text-neutral-500">{label}</span>
            <span className="text-xs font-medium text-neutral-800 tabular-nums">
              {pct}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Panel ────────────────────────────────────────────────────────────────────

export function SentimentPanel() {
  const { sentiment, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (!sentiment) return 'loading';
    if (!sentiment.available) return 'unavailable';
    return 'populated';
  })();

  const isLoading = status === 'loading' || status === 'streaming';

  return (
    <Panel id="sentiment" title="Sentiment Analysis" status={panelStatus}>
      {!sentiment && isLoading ? (
        <PanelSkeleton rows={3} />
      ) : !sentiment || !sentiment.available || !sentiment.distribution ? (
        <ErrorState message="Sentiment analysis is unavailable for this report." />
      ) : (
        <div className="px-4 pb-4 pt-2 space-y-4">
          {/* Distribution bar */}
          <SentimentBar distribution={sentiment.distribution} />

          {/* Dominant label */}
          {sentiment.dominant && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-neutral-500">Overall:</span>
              <SentimentBadge sentiment={sentiment.dominant} />
            </div>
          )}

          {/* Article count */}
          <p className="text-xs text-neutral-400">
            Based on {sentiment.article_count} article
            {sentiment.article_count !== 1 ? 's' : ''}
          </p>

          {/* Limited data caveat */}
          {sentiment.limited_data_caveat && (
            <p
              role="note"
              className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1"
            >
              Limited data — fewer than 3 articles analysed. Results may not
              be representative.
            </p>
          )}
        </div>
      )}
    </Panel>
  );
}
