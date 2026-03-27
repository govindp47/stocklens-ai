'use client';

/**
 * PriceTrendChart — panel wrapping the Recharts line chart.
 *
 * Accessibility strategy:
 * - The Recharts SVG chart is wrapped in aria-hidden="true" — it conveys
 *   no information that is not already in the visually-hidden data table.
 * - A <table> with OHLCV data is rendered outside the dynamic import so it
 *   is available in the DOM at all times (including SSR).
 * - The dynamic import uses { ssr: false } to prevent Recharts hydration errors.
 */

import dynamic from 'next/dynamic';
import { useAnalysisStore } from '@/store';
import { Panel } from '@/components/ui/Panel';
import { PanelSkeleton } from '@/components/ui/PanelSkeleton';
import { formatDate, formatPrice } from '@/lib/formatters';

// ─── Dynamic import (no SSR) ──────────────────────────────────────────────────

const PriceTrendChartClient = dynamic(
  () => import('./PriceTrendChartClient'),
  {
    ssr: false,
    loading: () => <PanelSkeleton rows={4} />,
  },
);

// ─── Panel ────────────────────────────────────────────────────────────────────

export function PriceTrendChart() {
  const { priceHistory, status, company } = useAnalysisStore();

  const panelStatus = (() => {
    if (!priceHistory) return 'loading';
    if (!priceHistory.available) return 'unavailable';
    return 'populated';
  })();

  const isLoading = status === 'loading' || (!priceHistory && status === 'streaming');

  return (
    <Panel id="price_chart" title="Price Trend" status={panelStatus}>
      {isLoading ? (
        <PanelSkeleton rows={4} />
      ) : !priceHistory?.available || priceHistory.datapoints.length === 0 ? (
        <div className="p-4 text-sm text-neutral-500 text-center">
          Price history unavailable for this ticker.
        </div>
      ) : (
        <div className="px-2 pb-4 pt-2">
          {/* ── Visual chart (aria-hidden — data is in the table below) ── */}
          <div aria-hidden="true">
            <PriceTrendChartClient datapoints={priceHistory.datapoints} />
          </div>

          {/* ── Trend / volatility badge ─────────────────────────────── */}
          {priceHistory.trend_direction && (
            <p className="mt-1 text-xs text-neutral-500 text-right pr-2">
              Trend: <span className="font-medium capitalize">{priceHistory.trend_direction}</span>
              {priceHistory.volatility_flag && (
                <span className="ml-2 text-amber-600">⚠ High volatility</span>
              )}
            </p>
          )}

          {/* ── Accessible data table (visually hidden, always in DOM) ── */}
          <div className="sr-only">
            <table>
              <caption>
                Historical closing prices for {company?.ticker ?? 'this ticker'}
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
