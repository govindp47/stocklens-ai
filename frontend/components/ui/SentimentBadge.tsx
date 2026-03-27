/**
 * SentimentBadge — displays a sentiment label with BOTH an icon AND a color.
 *
 * WCAG requirement: never convey information via color alone.
 * Each sentiment value has a distinct icon shape in addition to its color.
 */

import { TrendingUp, Minus, TrendingDown } from 'lucide-react';

export type SentimentLabel = 'positive' | 'neutral' | 'negative';

interface SentimentBadgeProps {
  sentiment: SentimentLabel | string;
}

const SENTIMENT_CONFIG: Record<
  SentimentLabel,
  {
    Icon: React.FC<React.SVGProps<SVGSVGElement>>;
    colorClass: string;
    bgClass: string;
    label: string;
  }
> = {
  positive: {
    Icon: TrendingUp as React.FC<React.SVGProps<SVGSVGElement>>,
    colorClass: 'text-sentiment-positive',
    bgClass: 'bg-green-50',
    label: 'Positive',
  },
  neutral: {
    Icon: Minus as React.FC<React.SVGProps<SVGSVGElement>>,
    colorClass: 'text-sentiment-neutral',
    bgClass: 'bg-amber-50',
    label: 'Neutral',
  },
  negative: {
    Icon: TrendingDown as React.FC<React.SVGProps<SVGSVGElement>>,
    colorClass: 'text-sentiment-negative',
    bgClass: 'bg-red-50',
    label: 'Negative',
  },
};

const FALLBACK = {
  Icon: Minus as React.FC<React.SVGProps<SVGSVGElement>>,
  colorClass: 'text-neutral-500',
  bgClass: 'bg-neutral-50',
  label: 'Unknown',
};

export function SentimentBadge({ sentiment }: SentimentBadgeProps) {
  const key = sentiment.toLowerCase() as SentimentLabel;
  const config = SENTIMENT_CONFIG[key] ?? { ...FALLBACK, label: sentiment };
  const { Icon, colorClass, bgClass, label } = config;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${colorClass} ${bgClass}`}
      aria-label={`Sentiment: ${label}`}
    >
      <Icon className="w-3 h-3" aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}
