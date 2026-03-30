'use client';

/**
 * ReportGrid — assembles all eight report panels in a two-column grid layout.
 *
 * Layout:
 * - Desktop: two-column grid
 * - Mobile: single column
 *
 * All panels are always rendered (never conditionally mounted) — they show
 * PanelSkeleton internally when their data is not yet available.
 */

import { StockOverviewPanel } from '@/components/panels/StockOverviewPanel';
import { PriceTrendChart } from '@/components/panels/PriceTrendChart';
import { NewsSummaryPanel } from '@/components/panels/NewsSummaryPanel';
import { SentimentPanel } from '@/components/panels/SentimentPanel';
import { EventsPanel } from '@/components/panels/EventsPanel';
import { InsightPanel } from '@/components/panels/InsightPanel';
import { DataSourcesPanel } from '@/components/panels/DataSourcesPanel';

export function ReportGrid() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">
      {/* Row 1 */}
      <StockOverviewPanel />
      <PriceTrendChart />

      {/* Row 2 */}
      <NewsSummaryPanel />
      <SentimentPanel />

      {/* Row 3 */}
      <EventsPanel />
      <InsightPanel />

      {/* Row 4 — full width */}
      <div className="md:col-span-2">
        <DataSourcesPanel />
      </div>
    </div>
  );
}
