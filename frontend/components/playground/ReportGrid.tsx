"use client";

/**
 * ReportGrid — assembles all report panels in a responsive grid.
 *
 * Layout (12-column grid on large screens):
 * - Row 1: Stock Overview (5) + Price Chart (7)
 * - Row 2: News Summary (7) + Sentiment (5)
 * - Row 3: Events (5) + AI Insight (7)
 * - Row 4: Data Sources (12, full width)
 */

import { StockOverviewPanel } from "@/components/panels/StockOverviewPanel";
import { PriceTrendChart } from "@/components/panels/PriceTrendChart";
import { NewsSummaryPanel } from "@/components/panels/NewsSummaryPanel";
import { SentimentPanel } from "@/components/panels/SentimentPanel";
import { EventsPanel } from "@/components/panels/EventsPanel";
import { InsightPanel } from "@/components/panels/InsightPanel";
import { DataSourcesPanel } from "@/components/panels/DataSourcesPanel";

export function ReportGrid() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-12 gap-4 w-full animate-fade-in-up">
      {/* Row 1 */}
      <div className="lg:col-span-5">
        <StockOverviewPanel />
      </div>
      <div className="lg:col-span-7">
        <PriceTrendChart />
      </div>

      {/* Row 2 */}
      <div className="lg:col-span-7">
        <NewsSummaryPanel />
      </div>
      <div className="lg:col-span-5">
        <SentimentPanel />
      </div>

      {/* Row 3 */}
      <div className="lg:col-span-5">
        <EventsPanel />
      </div>
      <div className="lg:col-span-7">
        <InsightPanel />
      </div>

      {/* Row 4 — full width */}
      <div className="md:col-span-2 lg:col-span-12">
        <DataSourcesPanel />
      </div>
    </div>
  );
}
