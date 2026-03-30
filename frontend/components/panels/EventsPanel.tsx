'use client';

/**
 * EventsPanel — extracted business event cards from news analysis.
 *
 * Accessibility:
 * - Empty state renders a descriptive paragraph.
 * - Error state uses ErrorState component with role="alert".
 */

import { useAnalysisStore } from '@/store';
import { Panel } from '@/components/ui/Panel';
import { PanelSkeleton } from '@/components/ui/PanelSkeleton';
import { ErrorState } from '@/components/ui/ErrorState';
import { formatDate } from '@/lib/formatters';
import type { ExtractedEvent } from '@/types/report';

// ─── Event card ───────────────────────────────────────────────────────────────

function EventCard({ event }: { event: ExtractedEvent }) {
  return (
    <div className="border-b border-neutral-100 last:border-0 px-4 py-3">
      <div className="flex items-start gap-2">
        {/* Event type badge */}
        <span className="shrink-0 mt-0.5 px-2 py-0.5 rounded-full text-xs font-medium bg-brand-50 text-brand-500 border border-brand-500/20">
          {event.event_type}
        </span>
      </div>
      {/* Description */}
      <p className="mt-1.5 text-xs text-neutral-700 leading-relaxed">
        {event.description}
      </p>
      {/* Detected date */}
      <p className="mt-1 text-xs text-neutral-400">
        Detected: {formatDate(event.detected_date)}
      </p>
    </div>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EventsEmptyState() {
  return (
    <p className="p-4 text-sm text-neutral-500 italic">
      No significant events identified.
    </p>
  );
}

// ─── Panel ────────────────────────────────────────────────────────────────────

export function EventsPanel() {
  const { events, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (!events) return 'loading';
    if (!events.available) return 'unavailable';
    return events.events.length === 0 ? 'populated' : 'populated';
  })();

  const isLoading = status === 'loading' || status === 'streaming';

  return (
    <Panel id="events" title="Key Events" status={panelStatus}>
      {!events && isLoading ? (
        <PanelSkeleton rows={3} />
      ) : !events || !events.available ? (
        <ErrorState message="Event extraction is unavailable for this report." />
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
