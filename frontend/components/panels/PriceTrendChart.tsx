"use client";

/**
 * PriceTrendChart — panel wrapping the Recharts line chart.
 *
 * Accessibility strategy:
 * - The Recharts SVG chart is wrapped in aria-hidden="true".
 * - A <table> with OHLCV data is rendered in the DOM at all times (sr-only).
 * - Dynamic import uses { ssr: false } to prevent Recharts hydration errors.
 */

import dynamic from "next/dynamic";
import { useAnalysisStore, useUIStore } from "@/store";
import { Panel } from "@/components/ui/Panel";
import { PanelSkeleton } from "@/components/ui/PanelSkeleton";
import { formatDate, formatPrice } from "@/lib/formatters";
import type { ActiveTimeframe } from "@/store/uiSlice";

const PriceTrendChartClient = dynamic(() => import("./PriceTrendChartClient"), {
  ssr: false,
  loading: () => <PanelSkeleton rows={4} />,
});

const TIMEFRAMES: ActiveTimeframe[] = ["1M", "3M"];

const TREND_LABELS: Record<string, { text: string; color: string }> = {
  up: { text: "↑ Upward", color: "text-sentiment-positive" },
  down: { text: "↓ Downward", color: "text-sentiment-negative" },
  sideways: { text: "→ Sideways", color: "text-muted-foreground" },
};

export function PriceTrendChart() {
  const { priceHistory, status, company } = useAnalysisStore();
  const { activeTimeframe, setTimeframe } = useUIStore();

  const panelStatus = (() => {
    if (!priceHistory) return "loading";
    if (!priceHistory.available) return "unavailable";
    return "populated";
  })();

  const isLoading =
    !priceHistory && (status === "loading" || status === "streaming");

  return (
    <Panel id="price_chart" title="Price Trend" status={panelStatus}>
      {isLoading ? (
        <PanelSkeleton rows={4} />
      ) : !priceHistory?.available || priceHistory.datapoints.length === 0 ? (
        <div className="p-6 text-center text-xs text-muted-foreground">
          Price history unavailable for this ticker.
        </div>
      ) : (
        <div className="pb-3 pt-2">
          {/* ── Timeframe toggles ─────────────────────────────────────── */}
          <div className="flex items-center justify-between px-4 mb-3">
            {/* Trend label */}
            <div className="flex items-center gap-2">
              {priceHistory.trend_direction && (
                <span
                  className={`text-xs font-semibold ${TREND_LABELS[priceHistory.trend_direction]?.color ?? "text-muted-foreground"}`}
                >
                  {TREND_LABELS[priceHistory.trend_direction]?.text ??
                    `→ ${priceHistory.trend_direction}`}
                </span>
              )}
              {priceHistory.volatility_flag && (
                <span className="inline-flex items-center gap-0.5 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700">
                  ⚠ Volatile
                </span>
              )}
            </div>

            {/* Timeframe buttons */}
            <div
              className="flex gap-0.5 rounded-lg border border-border bg-muted p-0.5"
              role="group"
              aria-label="Chart timeframe"
            >
              {TIMEFRAMES.map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  aria-pressed={activeTimeframe === tf}
                  className={`min-h-[28px] min-w-[32px] rounded-md px-2 py-1 text-xs font-medium transition-all duration-100
                    focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-0
                    ${
                      activeTimeframe === tf
                        ? "bg-surface text-brand-500 font-semibold shadow-panel"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>

          {/* ── Visual chart ────────────────────────────────────────────── */}
          <div aria-hidden="true" className="px-1">
            <PriceTrendChartClient datapoints={priceHistory.datapoints} />
          </div>

          {/* ── Accessible data table ────────────────────────────────────── */}
          <div className="sr-only">
            <table>
              <caption>
                Historical closing prices for {company?.ticker ?? "this ticker"}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Open</th>
                  <th scope="col">High</th>
                  <th scope="col">Low</th>
                  <th scope="col">Close</th>
                </tr>
              </thead>
              <tbody>
                {priceHistory.datapoints.map((point) => (
                  <tr key={point.date}>
                    <td>{formatDate(point.date)}</td>
                    <td>{formatPrice(point.open)}</td>
                    <td>{formatPrice(point.high)}</td>
                    <td>{formatPrice(point.low)}</td>
                    <td>{formatPrice(point.close)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Panel>
  );
}
