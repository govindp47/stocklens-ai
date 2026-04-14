"use client";

/**
 * Panel — base collapsible panel shell.
 *
 * Accessibility:
 * - Native <button> toggle with aria-expanded, aria-controls, aria-label.
 * - Heading (h2) is a sibling of the button — not nested inside it (WCAG).
 * - Panel content region has role="region" labelled by heading via aria-labelledby.
 */

import React from "react";
import { ChevronDown } from "lucide-react";
import { StatusIndicator } from "./StatusIndicator";
import { useUIStore } from "@/store";
import type { PanelId } from "@/store/uiSlice";

export type PanelStatus =
  | "loading"
  | "populated"
  | "partial"
  | "error"
  | "unavailable";

export interface PanelProps {
  id: PanelId;
  title: string;
  status: PanelStatus;
  badge?: React.ReactNode;
  partialNotice?: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}

export function Panel({
  id,
  title,
  status,
  badge,
  partialNotice,
  defaultExpanded = true,
  children,
}: PanelProps) {
  const { panelExpansion, togglePanel } = useUIStore();
  const isExpanded = panelExpansion[id] ?? defaultExpanded;
  const isPopulated = status === "populated" || status === "partial";

  return (
    <section
      aria-labelledby={`panel-title-${id}`}
      className={`rounded-2xl border border-border bg-surface overflow-hidden transition-shadow duration-200
        ${
          isPopulated
            ? "animate-fade-in-up shadow-panel hover:shadow-panel-hover"
            : "shadow-panel"
        }`}
    >
      {/* ── Header / toggle ────────────────────────────────────────────── */}
      <div className="flex min-h-[52px] items-center justify-between px-5 py-3 border-b border-border/50">
        <div className="flex items-center gap-2.5 min-w-0">
          <h2
            id={`panel-title-${id}`}
            className="text-sm font-semibold text-foreground truncate tracking-tight"
          >
            {title}
          </h2>
          {badge && <div className="shrink-0">{badge}</div>}
        </div>
        <button
          type="button"
          onClick={() => togglePanel(id)}
          aria-expanded={isExpanded}
          aria-controls={`panel-content-${id}`}
          aria-label={`${isExpanded ? "Collapse" : "Expand"} ${title} panel`}
          className="ml-3 flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1.5 text-muted-foreground
            hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500
            min-h-[36px] min-w-[36px] justify-center transition-colors duration-100"
        >
          <StatusIndicator status={status} />
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform duration-200 ${isExpanded ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>
      </div>

      {/* ── Partial data notice ─────────────────────────────────────────── */}
      {partialNotice && isExpanded && (
        <div
          role="alert"
          className="px-5 py-2 text-xs text-amber-700 bg-accent border-b border-border/40 flex items-center gap-1.5 dark:text-accent-foreground"
        >
          <span aria-hidden="true">⚠</span>
          {partialNotice}
        </div>
      )}

      {/* ── Collapsible content region ──────────────────────────────────── */}
      <div
        id={`panel-content-${id}`}
        role="region"
        aria-labelledby={`panel-title-${id}`}
        className={isExpanded ? "block" : "hidden"}
      >
        {children}
      </div>
    </section>
  );
}
