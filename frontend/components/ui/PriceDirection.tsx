/**
 * PriceDirection — conveys price change direction via color AND icon.
 * Never uses color alone (WCAG 2.1 AA).
 */

import { ArrowUp, ArrowDown, Minus } from "lucide-react";

interface PriceDirectionProps {
  changePct: number;
}

export function PriceDirection({ changePct }: PriceDirectionProps) {
  const isUp = changePct > 0;
  const isFlat = changePct === 0;
  const abs = Math.abs(changePct);

  const ariaLabel = isFlat
    ? "Unchanged"
    : `${isUp ? "Up" : "Down"} ${abs.toFixed(2)} percent`;

  const classes = isUp
    ? "bg-green-50 text-green-700 border border-green-200"
    : isFlat
      ? "bg-muted text-muted-foreground border border-border"
      : "bg-red-50 text-red-700 border border-red-200";

  return (
    <span
      className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums animate-fade-in-up ${classes}`}
      aria-label={ariaLabel}
    >
      {isUp ? (
        <ArrowUp className="h-3 w-3" aria-hidden="true" />
      ) : isFlat ? (
        <Minus className="h-3 w-3" aria-hidden="true" />
      ) : (
        <ArrowDown className="h-3 w-3" aria-hidden="true" />
      )}
      <span aria-hidden="true">
        {isUp ? "+" : isFlat ? "" : ""}
        {abs.toFixed(2)}%
      </span>
    </span>
  );
}
