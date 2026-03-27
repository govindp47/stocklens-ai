'use client';

/**
 * Panel — base collapsible panel shell.
 *
 * Accessibility:
 * - Toggle trigger has role="button", tabIndex={0}, aria-expanded, aria-controls.
 * - Enter key collapses/expands when the trigger is focused.
 * - Panel content region is identified with role="region".
 * - Section is labelled by its heading via aria-labelledby.
 */

import React from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { StatusIndicator } from './StatusIndicator';
import { useUIStore } from '@/store';
import type { PanelId } from '@/store/uiSlice';

export type PanelStatus = 'loading' | 'populated' | 'partial' | 'error' | 'unavailable';

export interface PanelProps {
  id: PanelId;
  title: string;
  status: PanelStatus;
  partialNotice?: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}

export function Panel({
  id,
  title,
  status,
  partialNotice,
  defaultExpanded = true,
  children,
}: PanelProps) {
  const { panelExpansion, togglePanel } = useUIStore();
  const isExpanded = panelExpansion[id] ?? defaultExpanded;

  return (
    <section
      aria-labelledby={`panel-title-${id}`}
      className="rounded-lg border border-neutral-200 bg-white shadow-sm"
    >
      {/* ── Header / toggle ────────────────────────────────────────────── */}
      <div
        className="flex min-h-[44px] items-center justify-between px-4 py-3 cursor-pointer select-none"
        onClick={() => togglePanel(id)}
        role="button"
        aria-expanded={isExpanded}
        aria-controls={`panel-content-${id}`}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            togglePanel(id);
          }
        }}
      >
        <h2
          id={`panel-title-${id}`}
          className="font-semibold text-sm text-neutral-800"
        >
          {title}
        </h2>
        <div className="flex items-center gap-2">
          <StatusIndicator status={status} />
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-neutral-400" aria-hidden="true" />
          ) : (
            <ChevronDown className="w-4 h-4 text-neutral-400" aria-hidden="true" />
          )}
        </div>
      </div>

      {/* ── Partial data notice ─────────────────────────────────────────── */}
      {partialNotice && (
        <div
          role="alert"
          className="px-4 py-1 text-xs text-amber-700 bg-amber-50 border-t border-amber-100"
        >
          ⚠ {partialNotice}
        </div>
      )}

      {/* ── Collapsible content region ──────────────────────────────────── */}
      <div
        id={`panel-content-${id}`}
        role="region"
        aria-labelledby={`panel-title-${id}`}
        className={isExpanded ? 'block' : 'hidden'}
      >
        {children}
      </div>
    </section>
  );
}
