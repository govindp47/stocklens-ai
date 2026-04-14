"use client";

/**
 * DataSourcesPanel — lists data providers with their status.
 * Defaults to collapsed.
 */

import { CheckCircle2, AlertCircle, XCircle } from "lucide-react";
import { useAnalysisStore } from "@/store";
import { Panel } from "@/components/ui/Panel";
import { PanelSkeleton } from "@/components/ui/PanelSkeleton";
import type { DataSource } from "@/types/report";

const MARKET_DATA_PROVIDERS = new Set([
  "yahoo finance",
  "alpha vantage",
  "polygon",
  "finnhub",
  "iex cloud",
  "quandl",
  "market data",
  "yfinance",
]);

function isMarketDataSource(source: DataSource): boolean {
  return MARKET_DATA_PROVIDERS.has(source.name.toLowerCase());
}

function SourceStatusIcon({ status }: { status: string }) {
  switch (status) {
    case "ok":
      return (
        <CheckCircle2
          className="h-3.5 w-3.5 text-sentiment-positive shrink-0"
          aria-hidden="true"
        />
      );
    case "partial":
      return (
        <AlertCircle
          className="h-3.5 w-3.5 text-sentiment-neutral shrink-0"
          aria-hidden="true"
        />
      );
    default:
      return (
        <XCircle
          className="h-3.5 w-3.5 text-sentiment-negative shrink-0"
          aria-hidden="true"
        />
      );
  }
}

const STATUS_BADGE: Record<string, string> = {
  ok: "bg-green-50 text-green-700 border border-green-200",
  partial: "bg-amber-50 text-amber-700 border border-amber-200",
  unavailable: "bg-red-50 text-red-700 border border-red-200",
};

function SourceRow({ source }: { source: DataSource }) {
  const badgeClass = STATUS_BADGE[source.status] ?? STATUS_BADGE.unavailable;
  return (
    <div className="flex items-center gap-2.5 border-b border-border/50 last:border-0 px-4 py-2.5">
      <SourceStatusIcon status={source.status} />
      <div className="min-w-0 flex-1">
        <span className="text-xs font-medium text-foreground">
          {source.name}
        </span>
        {source.detail && (
          <p className="text-[11px] text-muted-foreground truncate mt-0.5">
            {source.detail}
          </p>
        )}
      </div>
      <span
        className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold capitalize ${badgeClass}`}
      >
        {source.status}
      </span>
    </div>
  );
}

export function DataSourcesPanel() {
  const { dataSources, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (dataSources.length === 0) {
      if (status === "loading" || status === "streaming") return "loading";
      return "unavailable";
    }
    return "populated";
  })();

  const isLoading =
    dataSources.length === 0 &&
    (status === "loading" || status === "streaming");

  const marketDataSources = dataSources.filter(isMarketDataSource);
  const newsSources = dataSources.filter((s) => !isMarketDataSource(s));

  return (
    <Panel
      id="data_sources"
      title="Data Sources"
      status={panelStatus}
      defaultExpanded={false}
    >
      {isLoading ? (
        <PanelSkeleton rows={3} />
      ) : dataSources.length === 0 ? (
        <p className="p-4 text-xs text-muted-foreground">
          No data source information available.
        </p>
      ) : (
        <div className="pb-2">
          {marketDataSources.length > 0 && (
            <div>
              <p className="px-4 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Market Data
              </p>
              {marketDataSources.map((s) => (
                <SourceRow key={s.name} source={s} />
              ))}
            </div>
          )}
          {newsSources.length > 0 && (
            <div>
              <p className="px-4 pt-3 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                News Sources
              </p>
              {newsSources.map((s) => (
                <SourceRow key={s.name} source={s} />
              ))}
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
