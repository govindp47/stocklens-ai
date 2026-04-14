"use client";

/**
 * SentimentPanel — sentiment distribution bar and dominant label.
 *
 * Accessibility:
 * - Each bar segment has aria-label communicating the percentage textually.
 * - Color alone is never the sole indicator — segment labels are always visible.
 * - SentimentBadge also uses icon + text, not color alone.
 */

import { AlertTriangle } from "lucide-react";
import { useAnalysisStore } from "@/store";
import { Panel } from "@/components/ui/Panel";
import { PanelSkeleton } from "@/components/ui/PanelSkeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { SentimentBadge } from "@/components/ui/SentimentBadge";
import type { SentimentDistribution } from "@/types/report";

// ─── Sentiment bar ────────────────────────────────────────────────────────────

function SentimentBar({
  distribution,
}: {
  distribution: SentimentDistribution;
}) {
  const { positive, neutral, negative } = distribution;

  const segments = [
    {
      key: "positive",
      pct: positive,
      bg: "bg-sentiment-positive",
      label: "Positive",
    },
    {
      key: "neutral",
      pct: neutral,
      bg: "bg-sentiment-neutral",
      label: "Neutral",
    },
    {
      key: "negative",
      pct: negative,
      bg: "bg-sentiment-negative",
      label: "Negative",
    },
  ];

  return (
    <div>
      {/* Segmented bar */}
      <div
        className="flex h-7 w-full rounded-lg overflow-hidden gap-px"
        role="img"
        aria-label={`Sentiment: Positive ${positive}%, Neutral ${neutral}%, Negative ${negative}%`}
      >
        {segments.map(({ key, pct, bg, label }) =>
          pct > 0 ? (
            <div
              key={key}
              className={`${bg} flex items-center justify-center transition-all duration-700`}
              style={{ width: `${pct}%` }}
              aria-label={`${label}: ${pct}%`}
            >
              {pct >= 12 && (
                <span className="text-white text-xs font-semibold select-none drop-shadow-sm">
                  {pct}%
                </span>
              )}
            </div>
          ) : null,
        )}
      </div>

      {/* Legend */}
      <div className="flex justify-between mt-2.5 px-0.5">
        {segments.map(({ key, pct, label }) => (
          <div key={key} className="flex flex-col items-center gap-0.5">
            <span className="text-[11px] font-semibold tabular-nums text-foreground">
              {pct}%
            </span>
            <span className="text-[10px] text-muted-foreground">{label}</span>
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
    if (!sentiment) return "loading";
    if (!sentiment.available) return "unavailable";
    return "populated";
  })();

  const isLoading =
    !sentiment && (status === "loading" || status === "streaming");

  return (
    <Panel id="sentiment" title="News Sentiment" status={panelStatus}>
      {isLoading ? (
        <PanelSkeleton rows={3} />
      ) : !sentiment || !sentiment.available || !sentiment.distribution ? (
        <ErrorState message="Sentiment analysis unavailable." />
      ) : (
        <div className="px-5 pb-5 pt-4 space-y-4">
          {/* Emerging concern alert */}
          {sentiment.emerging_concern_flag && (
            <div
              role="alert"
              className="flex items-start gap-2.5 rounded-xl border border-amber-200/70 bg-accent px-3.5 py-2.5 dark:border-amber-800/40"
            >
              <AlertTriangle
                className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5"
                aria-hidden="true"
              />
              <p className="text-xs text-amber-800 leading-relaxed dark:text-accent-foreground">
                Unusual increase in negative sentiment detected
              </p>
            </div>
          )}

          {/* Distribution bar */}
          <SentimentBar distribution={sentiment.distribution} />

          {/* Dominant sentiment + article count */}
          <div className="flex items-center justify-between pt-1">
            {sentiment.dominant && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Overall:</span>
                <SentimentBadge sentiment={sentiment.dominant} />
              </div>
            )}
            <span className="text-xs text-muted-foreground">
              {sentiment.article_count} article
              {sentiment.article_count !== 1 ? "s" : ""}
            </span>
          </div>

          {sentiment.limited_data_caveat && (
            <p role="note" className="text-xs text-muted-foreground italic">
              Based on limited data — results may not be representative
            </p>
          )}
        </div>
      )}
    </Panel>
  );
}
