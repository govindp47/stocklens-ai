'use client';

/**
 * DataSourcesPanel — lists data providers with their status and fetch timestamps.
 *
 * Defaults to collapsed (defaultExpanded={false}) per T-049 spec.
 */

import { CheckCircle2, AlertCircle, XCircle } from 'lucide-react';
import { useAnalysisStore } from '@/store';
import { Panel } from '@/components/ui/Panel';
import { PanelSkeleton } from '@/components/ui/PanelSkeleton';
import type { DataSource } from '@/types/report';

// ─── Status icon ──────────────────────────────────────────────────────────────

function SourceStatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'ok':
      return (
        <CheckCircle2
          className="w-3.5 h-3.5 text-sentiment-positive shrink-0"
          aria-hidden="true"
        />
      );
    case 'partial':
      return (
        <AlertCircle
          className="w-3.5 h-3.5 text-sentiment-neutral shrink-0"
          aria-hidden="true"
        />
      );
    default:
      return (
        <XCircle
          className="w-3.5 h-3.5 text-sentiment-negative shrink-0"
          aria-hidden="true"
        />
      );
  }
}

// ─── Source row ───────────────────────────────────────────────────────────────

function SourceRow({ source }: { source: DataSource }) {
  return (
    <div className="flex items-start gap-2 border-b border-neutral-100 last:border-0 px-4 py-2.5">
      <SourceStatusIcon status={source.status} />
      <div className="min-w-0 flex-1">
        <span className="text-xs font-medium text-neutral-800">{source.name}</span>
        {source.detail && (
          <p className="text-xs text-neutral-500 truncate">{source.detail}</p>
        )}
      </div>
      <span
        className={`text-xs px-1.5 py-0.5 rounded-full ${
          source.status === 'ok'
            ? 'bg-green-50 text-green-700'
            : source.status === 'partial'
            ? 'bg-amber-50 text-amber-700'
            : 'bg-red-50 text-red-700'
        }`}
      >
        {source.status}
      </span>
    </div>
  );
}

// ─── Panel ────────────────────────────────────────────────────────────────────

export function DataSourcesPanel() {
  const { dataSources, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (dataSources.length === 0) {
      if (status === 'loading' || status === 'streaming') return 'loading';
      return 'unavailable';
    }
    return 'populated';
  })();

  const isLoading = status === 'loading' || status === 'streaming';

  return (
    <Panel
      id="data_sources"
      title="Data Sources"
      status={panelStatus}
      defaultExpanded={false}
    >
      {dataSources.length === 0 && isLoading ? (
        <PanelSkeleton rows={3} />
      ) : dataSources.length === 0 ? (
        <p className="p-4 text-xs text-neutral-500">No data source information available.</p>
      ) : (
        <div>
          {dataSources.map((source) => (
            <SourceRow key={source.name} source={source} />
          ))}
        </div>
      )}
    </Panel>
  );
}
