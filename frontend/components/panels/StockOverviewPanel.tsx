"use client";

/**
 * StockOverviewPanel — company metadata, current price, and key market metrics.
 */

import { Building2, Clock } from "lucide-react";
import { useAnalysisStore } from "@/store";
import { Panel } from "@/components/ui/Panel";
import { PanelSkeleton } from "@/components/ui/PanelSkeleton";
import { PriceDirection } from "@/components/ui/PriceDirection";
import {
  formatPrice,
  formatLargeNumber,
  formatVolume,
  formatRatio,
} from "@/lib/formatters";

// ─── Metric card ──────────────────────────────────────────────────────────────

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-border/40 last:border-0">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-xs font-semibold text-foreground tabular-nums">
        {value}
      </dd>
    </div>
  );
}

// ─── Panel content ────────────────────────────────────────────────────────────

export function StockOverviewPanel() {
  const { company, marketData, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (!marketData) return "loading";
    if (!marketData.available) return "unavailable";
    return "populated";
  })();

  const title = company
    ? `${company.ticker}${company.name ? ` · ${company.name}` : ""}`
    : "Stock Overview";

  return (
    <Panel id="stock_overview" title={title} status={panelStatus}>
      {!marketData ? (
        <PanelSkeleton rows={5} hero />
      ) : !marketData.available ? (
        <div className="px-5 py-8 text-center text-xs text-muted-foreground">
          Market data unavailable for this ticker.
        </div>
      ) : (
        <div className="px-5 pb-5">
          {/* ── Price hero ──────────────────────────────────────────── */}
          <div className="flex items-baseline gap-3 pt-5 pb-4 border-b border-border/40">
            <span className="text-3xl font-bold tabular-nums text-foreground tracking-tight">
              {formatPrice(marketData.price, marketData.currency)}
            </span>
            {marketData.change_pct != null && (
              <PriceDirection changePct={marketData.change_pct} />
            )}
          </div>

          {/* ── Company info badges ──────────────────────────────────── */}
          {company && (company.sector || company.exchange) && (
            <div className="py-3 flex flex-wrap items-center gap-x-2 gap-y-1.5 border-b border-border/40">
              {company.sector && (
                <span className="inline-flex items-center gap-1.5 rounded-lg bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                  <Building2 className="h-3 w-3" aria-hidden="true" />
                  {company.sector}
                </span>
              )}
              {company.exchange && (
                <span className="inline-flex items-center rounded-lg bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                  {company.exchange}
                </span>
              )}
              {company.country && (
                <span className="inline-flex items-center rounded-lg bg-muted px-2.5 py-1 text-[11px] font-medium text-muted-foreground">
                  {company.country}
                </span>
              )}
            </div>
          )}

          {/* ── Key metrics ───────────────────────────────────────────── */}
          <dl className="pt-1">
            <MetricRow
              label="Market Cap"
              value={formatLargeNumber(
                marketData.market_cap,
                marketData.currency,
              )}
            />
            <MetricRow label="Volume" value={formatVolume(marketData.volume)} />
            <MetricRow
              label="P/E Ratio"
              value={formatRatio(marketData.pe_ratio)}
            />
            <MetricRow
              label="52-Week High"
              value={formatPrice(marketData.week_52_high, marketData.currency)}
            />
            <MetricRow
              label="52-Week Low"
              value={formatPrice(marketData.week_52_low, marketData.currency)}
            />
          </dl>

          <div className="mt-4 flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <Clock className="h-3 w-3" aria-hidden="true" />
            <span>
              Data may be delayed up to {marketData.data_delayed_minutes} min
            </span>
          </div>
        </div>
      )}
    </Panel>
  );
}
