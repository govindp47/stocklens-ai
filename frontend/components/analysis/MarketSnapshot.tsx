"use client";

import type { MarketData, CompanyInfo } from "@/types/report";
import {
  formatPrice,
  formatChangePct,
  formatLargeNumber,
  formatVolume,
  formatRatio,
} from "@/lib/formatters";
import { TrendingUp, TrendingDown, Minus } from "lucide-react";

export function MarketSnapshot({
  marketData,
  company,
}: {
  marketData: MarketData;
  company: CompanyInfo;
}) {
  const changeDir =
    (marketData.change_pct ?? 0) > 0
      ? "up"
      : (marketData.change_pct ?? 0) < 0
        ? "down"
        : null;

  const ChangeIcon =
    changeDir === "up"
      ? TrendingUp
      : changeDir === "down"
        ? TrendingDown
        : Minus;

  const metrics = [
    {
      label: "Market Cap",
      value: formatLargeNumber(marketData.market_cap, marketData.currency),
      color: null,
    },
    {
      label: "P/E Ratio",
      value: formatRatio(marketData.pe_ratio),
      color: null,
    },
    {
      label: "52W High",
      value: formatPrice(marketData.week_52_high, marketData.currency),
      color: "text-emerald-600 dark:text-emerald-400",
    },
    {
      label: "52W Low",
      value: formatPrice(marketData.week_52_low, marketData.currency),
      color: "text-red-500 dark:text-red-400",
    },
    { label: "Volume", value: formatVolume(marketData.volume), color: null },
    { label: "Exchange", value: company?.exchange ?? "N/A", color: null },
  ];

  return (
    <section aria-label="Market snapshot" className="px-5 pt-4 pb-5">
      {/* ── Price hero ──────────────────────────────────────────────────── */}
      <div className="flex items-end gap-3 mb-5">
        <span className="text-5xl font-black tabular-nums tracking-tight text-foreground leading-none">
          {formatPrice(marketData.price, marketData.currency)}
        </span>
        {marketData.change_pct != null && (
          <div
            className={`flex items-center gap-1.5 mb-1 text-sm font-semibold ${
              changeDir === "up"
                ? "text-emerald-600 dark:text-emerald-400"
                : changeDir === "down"
                  ? "text-red-500 dark:text-red-400"
                  : "text-muted-foreground"
            }`}
          >
            <ChangeIcon className="h-4 w-4" aria-hidden="true" />
            <span>{formatChangePct(marketData.change_pct)}</span>
            {marketData.change_abs != null && (
              <span className="font-normal text-muted-foreground text-xs">
                ({formatPrice(marketData.change_abs, marketData.currency)})
              </span>
            )}
          </div>
        )}
        {marketData.data_delayed_minutes > 0 && (
          <span className="mb-1 text-[10px] text-muted-foreground ml-auto">
            {marketData.data_delayed_minutes}min delayed
          </span>
        )}
      </div>

      {/* ── Bloomberg-style data strip ───────────────────────────────────── */}
      <div
        className="flex items-stretch gap-px bg-border rounded-xl overflow-x-auto"
        role="list"
        aria-label="Market metrics"
      >
        {metrics.map((m) => (
          <div
            key={m.label}
            role="listitem"
            className="flex flex-col gap-0.5 flex-1 px-4 py-3 bg-surface min-w-[80px]"
          >
            <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground whitespace-nowrap">
              {m.label}
            </span>
            <span
              className={`text-sm font-bold tabular-nums ${m.color ?? "text-foreground"}`}
            >
              {m.value}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}
