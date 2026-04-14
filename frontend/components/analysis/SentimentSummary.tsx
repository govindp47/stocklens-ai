"use client";

import type { SentimentResult } from "@/types/report";
import { TrendingUp, TrendingDown, Minus, AlertTriangle } from "lucide-react";

export function SentimentSummary({
  sentiment,
}: {
  sentiment: SentimentResult;
}) {
  if (!sentiment.available || !sentiment.distribution) {
    return (
      <p className="text-sm text-muted-foreground italic px-5 pb-5">
        Sentiment data unavailable.
      </p>
    );
  }

  const { positive, neutral, negative } = sentiment.distribution;
  const dominant = sentiment.dominant ?? "neutral";

  const pos = Math.round(positive);
  const neu = Math.round(neutral);
  const neg = Math.round(negative);

  const DominantIcon =
    dominant === "positive"
      ? TrendingUp
      : dominant === "negative"
        ? TrendingDown
        : Minus;
  const dominantColor =
    dominant === "positive"
      ? "text-emerald-600 dark:text-emerald-400"
      : dominant === "negative"
        ? "text-red-500 dark:text-red-400"
        : "text-muted-foreground";

  return (
    <section
      aria-label="Sentiment summary"
      className="px-5 pt-4 pb-5 space-y-4"
    >
      {/* Dominant indicator */}
      <div className="flex items-center gap-3">
        <DominantIcon
          className={`h-7 w-7 ${dominantColor} shrink-0`}
          aria-hidden="true"
        />
        <div>
          <span className={`text-xl font-bold capitalize ${dominantColor}`}>
            {dominant}
          </span>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            {sentiment.article_count} article
            {sentiment.article_count !== 1 ? "s" : ""} analysed
          </p>
        </div>
      </div>

      {/* Stacked proportion bar */}
      <div
        className="flex h-2.5 rounded-full overflow-hidden gap-px"
        role="img"
        aria-label={`Sentiment: ${pos}% positive, ${neu}% neutral, ${neg}% negative`}
      >
        {pos > 0 && (
          <div
            className="bg-emerald-500 transition-all duration-700 first:rounded-l-full last:rounded-r-full"
            style={{ width: `${pos}%` }}
          />
        )}
        {neu > 0 && (
          <div
            className="bg-amber-400 transition-all duration-700 first:rounded-l-full last:rounded-r-full"
            style={{ width: `${neu}%` }}
          />
        )}
        {neg > 0 && (
          <div
            className="bg-red-500 transition-all duration-700 first:rounded-l-full last:rounded-r-full"
            style={{ width: `${neg}%` }}
          />
        )}
      </div>

      {/* Legend */}
      <div className="flex gap-3 flex-wrap">
        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <div
            className="h-2 w-2 rounded-full bg-emerald-500 shrink-0"
            aria-hidden="true"
          />
          {pos}% positive
        </span>
        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <div
            className="h-2 w-2 rounded-full bg-amber-400 shrink-0"
            aria-hidden="true"
          />
          {neu}% neutral
        </span>
        <span className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <div
            className="h-2 w-2 rounded-full bg-red-500 shrink-0"
            aria-hidden="true"
          />
          {neg}% negative
        </span>
      </div>

      {/* Emerging concern flag */}
      {sentiment.emerging_concern_flag && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2 dark:bg-amber-950/30 dark:border-amber-800/40">
          <AlertTriangle
            className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400 shrink-0"
            aria-hidden="true"
          />
          <p className="text-xs text-amber-800 dark:text-amber-300">
            Unusual negative coverage concentration detected.
          </p>
        </div>
      )}
    </section>
  );
}
