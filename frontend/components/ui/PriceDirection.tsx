/**
 * PriceDirection — conveys price change direction via color AND a directional
 * arrow icon. Never uses color alone (WCAG 2.1 AA requirement).
 *
 * aria-label reads "Up 1.23 percent", "Down 0.50 percent", or "Unchanged"
 * so screen readers get the same information sighted users see.
 */

import { ArrowUp, ArrowDown, Minus } from 'lucide-react';

interface PriceDirectionProps {
  /** Percentage change value (positive = up, negative = down, zero = flat). */
  changePct: number;
}

export function PriceDirection({ changePct }: PriceDirectionProps) {
  const isUp = changePct > 0;
  const isFlat = changePct === 0;
  const abs = Math.abs(changePct);

  const directionLabel = isUp ? 'Up' : isFlat ? 'Unchanged' : 'Down';
  const ariaLabel = isFlat
    ? 'Unchanged'
    : `${directionLabel} ${abs.toFixed(2)} percent`;

  const colorClass = isUp
    ? 'text-sentiment-positive'
    : isFlat
      ? 'text-neutral-500'
      : 'text-sentiment-negative';

  return (
    <span
      className={`inline-flex items-center gap-1 font-medium tabular-nums ${colorClass}`}
      aria-label={ariaLabel}
    >
      {isUp ? (
        <ArrowUp className="w-3.5 h-3.5" aria-hidden="true" />
      ) : isFlat ? (
        <Minus className="w-3.5 h-3.5" aria-hidden="true" />
      ) : (
        <ArrowDown className="w-3.5 h-3.5" aria-hidden="true" />
      )}
      <span aria-hidden="true">
        {isUp ? '+' : isFlat ? '' : '-'}
        {abs.toFixed(2)}%
      </span>
    </span>
  );
}
