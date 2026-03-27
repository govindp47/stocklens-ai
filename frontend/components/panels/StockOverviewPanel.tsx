'use client';

/**
 * StockOverviewPanel — company metadata, current price, and key market metrics.
 *
 * Data flow: reads company and marketData directly from the Zustand store.
 * Renders PanelSkeleton while data is not yet available.
 */

import { useAnalysisStore } from '@/store';
import { Panel } from '@/components/ui/Panel';
import { PanelSkeleton } from '@/components/ui/PanelSkeleton';
import { PriceDirection } from '@/components/ui/PriceDirection';
import {
  formatPrice,
  formatLargeNumber,
  formatVolume,
  formatRatio,
} from '@/lib/formatters';

// ─── Metric row ───────────────────────────────────────────────────────────────

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-neutral-100 last:border-0">
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="text-xs font-medium text-neutral-800 tabular-nums">
        {value}
      </dd>
    </div>
  );
}

// ─── Panel content ────────────────────────────────────────────────────────────

export function StockOverviewPanel() {
  const { company, marketData, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (status === 'loading' || status === 'streaming') {
      return marketData ? 'populated' : 'loading';
    }
    if (!marketData?.available) return 'unavailable';
    return 'populated';
  })();

  return (
    <Panel
      id="stock_overview"
      title={company ? `${company.ticker} — ${company.name ?? company.ticker}` : 'Stock Overview'}
      status={panelStatus}
    >
      {!marketData ? (
        <PanelSkeleton rows={5} />
      ) : (
        <div className="px-4 pb-4">
          {/* ── Price header ──────────────────────────────────────────── */}
          <div className="flex items-end gap-3 py-3 border-b border-neutral-100">
            <span className="text-2xl font-bold text-neutral-900 tabular-nums">
              {formatPrice(marketData.price, marketData.currency)}
            </span>
            {marketData.change_pct != null && (
              <PriceDirection changePct={marketData.change_pct} />
            )}
          </div>

          {/* ── Company info ──────────────────────────────────────────── */}
          {company && (
            <div className="py-2 border-b border-neutral-100">
              {company.sector && (
                <p className="text-xs text-neutral-500">
                  {company.sector}
                  {company.industry ? ` · ${company.industry}` : ''}
                </p>
              )}
              {company.exchange && (
                <p className="text-xs text-neutral-400">{company.exchange}</p>
              )}
            </div>
          )}

          {/* ── Key metrics ───────────────────────────────────────────── */}
          <dl className="mt-2">
            <MetricRow
              label="Market Cap"
              value={formatLargeNumber(marketData.market_cap, marketData.currency)}
            />
            <MetricRow
              label="Volume"
              value={formatVolume(marketData.volume)}
            />
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

          {marketData.data_delayed_minutes > 0 && (
            <p className="mt-2 text-xs text-neutral-400 text-right">
              Data delayed ~{marketData.data_delayed_minutes} min
            </p>
          )}
        </div>
      )}
    </Panel>
  );
}
