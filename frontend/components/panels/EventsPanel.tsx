"use client";

/**
 * EventsPanel — extracted business event cards from news analysis.
 */

import { Calendar, FileText } from "lucide-react";
import { useAnalysisStore } from "@/store";
import { Panel } from "@/components/ui/Panel";
import { PanelSkeleton } from "@/components/ui/PanelSkeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { formatDate } from "@/lib/formatters";
import type { ExtractedEvent } from "@/types/report";

const EVENT_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  earnings: {
    label: "Earnings",
    color: "bg-purple-50 text-purple-700 border-purple-200",
  },
  earnings_announcement: {
    label: "Earnings",
    color: "bg-purple-50 text-purple-700 border-purple-200",
  },
  acquisition: {
    label: "M&A",
    color: "bg-blue-50 text-blue-700 border-blue-200",
  },
  merger: { label: "M&A", color: "bg-blue-50 text-blue-700 border-blue-200" },
  ma: { label: "M&A", color: "bg-blue-50 text-blue-700 border-blue-200" },
  m_and_a: { label: "M&A", color: "bg-blue-50 text-blue-700 border-blue-200" },
  regulatory: {
    label: "Regulatory",
    color: "bg-amber-50 text-amber-700 border-amber-200",
  },
  regulatory_action: {
    label: "Regulatory",
    color: "bg-amber-50 text-amber-700 border-amber-200",
  },
  product_launch: {
    label: "Product",
    color: "bg-green-50 text-green-700 border-green-200",
  },
  product: {
    label: "Product",
    color: "bg-green-50 text-green-700 border-green-200",
  },
  leadership: {
    label: "Leadership",
    color: "bg-sky-50 text-sky-700 border-sky-200",
  },
  leadership_change: {
    label: "Leadership",
    color: "bg-sky-50 text-sky-700 border-sky-200",
  },
};

const DEFAULT_EVENT_COLOR = "bg-muted text-muted-foreground border-border";

function getEventConfig(eventType: string) {
  const key = eventType.toLowerCase().replace(/[^a-z0-9]/g, "_");
  return (
    EVENT_TYPE_CONFIG[key] ??
    EVENT_TYPE_CONFIG[eventType.toLowerCase()] ?? {
      label: eventType,
      color: DEFAULT_EVENT_COLOR,
    }
  );
}

// ─── Event card ───────────────────────────────────────────────────────────────

function EventCard({ event }: { event: ExtractedEvent }) {
  const { label, color } = getEventConfig(event.event_type);

  return (
    <div className="border-b border-border/50 last:border-0 px-4 py-4">
      <div className="flex items-start gap-2 mb-2">
        <span
          className={`shrink-0 inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${color}`}
        >
          {label}
        </span>
      </div>
      <p className="text-xs text-muted-foreground leading-relaxed">
        {event.description}
      </p>
      <div className="flex items-center gap-3 mt-2">
        {event.detected_date && (
          <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
            <Calendar className="h-3 w-3" aria-hidden="true" />
            {formatDate(event.detected_date)}
          </span>
        )}
        {event.source_article_indices.length > 0 && (
          <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
            <FileText className="h-3 w-3" aria-hidden="true" />
            {event.source_article_indices.length} source
            {event.source_article_indices.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EventsEmptyState() {
  return (
    <div className="flex flex-col items-center gap-2 py-8 px-4 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
        <Calendar
          className="h-5 w-5 text-muted-foreground"
          aria-hidden="true"
        />
      </div>
      <p className="text-xs text-muted-foreground">
        No significant events identified in the current news window.
      </p>
    </div>
  );
}

// ─── Panel ────────────────────────────────────────────────────────────────────

export function EventsPanel() {
  const { events, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (!events) return "loading";
    if (!events.available) return "unavailable";
    return "populated";
  })();

  const isLoading = !events && (status === "loading" || status === "streaming");
  const eventCount = events?.events?.length ?? 0;

  const badge =
    events && events.available && eventCount > 0 ? (
      <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">
        {eventCount}
      </span>
    ) : null;

  return (
    <Panel id="events" title="Key Events" status={panelStatus} badge={badge}>
      {isLoading ? (
        <PanelSkeleton rows={4} />
      ) : !events || !events.available ? (
        <ErrorState message="Event extraction unavailable." />
      ) : events.events.length === 0 ? (
        <EventsEmptyState />
      ) : (
        <div>
          {events.events.map((event, index) => (
            <EventCard
              key={`${event.event_type}-${event.detected_date}-${index}`}
              event={event}
            />
          ))}
        </div>
      )}
    </Panel>
  );
}
