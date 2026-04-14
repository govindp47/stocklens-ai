/**
 * SentimentBadge — displays a sentiment label with BOTH an icon AND a color.
 *
 * WCAG requirement: never convey information via color alone.
 * Each sentiment value has a distinct icon shape in addition to its color.
 */

import { TrendingUp, Minus, TrendingDown } from "lucide-react";

export type SentimentLabel = "positive" | "neutral" | "negative";

interface SentimentBadgeProps {
  sentiment: SentimentLabel | string;
}

const SENTIMENT_CONFIG: Record<
  SentimentLabel,
  {
    Icon: React.FC<React.SVGProps<SVGSVGElement>>;
    classes: string;
    label: string;
  }
> = {
  positive: {
    Icon: TrendingUp as React.FC<React.SVGProps<SVGSVGElement>>,
    classes: "bg-green-50 text-green-700 border border-green-200",
    label: "Positive",
  },
  neutral: {
    Icon: Minus as React.FC<React.SVGProps<SVGSVGElement>>,
    classes: "bg-amber-50 text-amber-700 border border-amber-200",
    label: "Neutral",
  },
  negative: {
    Icon: TrendingDown as React.FC<React.SVGProps<SVGSVGElement>>,
    classes: "bg-red-50 text-red-700 border border-red-200",
    label: "Negative",
  },
};

const FALLBACK = {
  Icon: Minus as React.FC<React.SVGProps<SVGSVGElement>>,
  classes: "bg-muted text-muted-foreground border border-border",
  label: "Unknown",
};

export function SentimentBadge({ sentiment }: SentimentBadgeProps) {
  const key = sentiment.toLowerCase() as SentimentLabel;
  const config = SENTIMENT_CONFIG[key] ?? { ...FALLBACK, label: sentiment };
  const { Icon, classes, label } = config;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${classes}`}
      aria-label={`Sentiment: ${label}`}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}
