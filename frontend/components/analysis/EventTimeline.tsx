"use client";

import type { EventsResult } from "@/types/report";
import { formatDate } from "@/lib/formatters";
import { Calendar } from "lucide-react";

// ─── Event type color palettes ────────────────────────────────────────────────

const EVENT_CHIP_COLORS: Record<string, string> = {
  earnings:
    "bg-violet-100 text-violet-700 dark:bg-violet-950/40 dark:text-violet-400",
  merger: "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400",
  acquisition:
    "bg-blue-100 text-blue-700 dark:bg-blue-950/40 dark:text-blue-400",
  partnership: "bg-sky-100 text-sky-700 dark:bg-sky-950/40 dark:text-sky-400",
  product_launch:
    "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400",
  regulatory:
    "bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400",
  leadership:
    "bg-slate-100 text-slate-600 dark:bg-slate-800/60 dark:text-slate-300",
  legal: "bg-red-100 text-red-700 dark:bg-red-950/40 dark:text-red-400",
  dividend: "bg-teal-100 text-teal-700 dark:bg-teal-950/40 dark:text-teal-400",
  macro: "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400",
};

const EVENT_ICON_COLORS: Record<string, string> = {
  earnings:
    "bg-violet-100 text-violet-600 dark:bg-violet-950/50 dark:text-violet-400",
  merger: "bg-blue-100 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400",
  acquisition:
    "bg-blue-100 text-blue-600 dark:bg-blue-950/50 dark:text-blue-400",
  partnership: "bg-sky-100 text-sky-600 dark:bg-sky-950/50 dark:text-sky-400",
  product_launch:
    "bg-emerald-100 text-emerald-600 dark:bg-emerald-950/50 dark:text-emerald-400",
  regulatory:
    "bg-amber-100 text-amber-600 dark:bg-amber-950/50 dark:text-amber-400",
  leadership:
    "bg-slate-100 text-slate-500 dark:bg-slate-800/60 dark:text-slate-300",
  legal: "bg-red-100 text-red-600 dark:bg-red-950/50 dark:text-red-400",
  dividend: "bg-teal-100 text-teal-600 dark:bg-teal-950/50 dark:text-teal-400",
  macro: "bg-rose-100 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400",
};

function normalizeKey(type: string): string {
  return type.toLowerCase().replace(/\s+/g, "_");
}

function eventChipColor(type: string): string {
  return (
    EVENT_CHIP_COLORS[normalizeKey(type)] ?? "bg-muted text-muted-foreground"
  );
}

function eventIconColor(type: string): string {
  return (
    EVENT_ICON_COLORS[normalizeKey(type)] ?? "bg-muted text-muted-foreground"
  );
}

function formatEventType(type: string): string {
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ─── Component ────────────────────────────────────────────────────────────────

export function EventTimeline({ events }: { events: EventsResult }) {
  if (!events.available || events.events.length === 0) {
    return (
      <p className="text-sm text-muted-foreground italic px-5 pb-5">
        No key events extracted.
      </p>
    );
  }

  return (
    <section aria-label="Key events timeline" className="px-5 pt-4 pb-5">
      <ol className="space-y-3">
        {events.events.map((ev, i) => (
          <li
            key={i}
            className="relative flex gap-3 animate-timeline-in"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            {/* Vertical spine connector */}
            {i < events.events.length - 1 && (
              <div
                className="absolute left-3.5 top-9 bottom-0 w-px bg-border/60"
                aria-hidden="true"
              />
            )}

            {/* Event type icon chip */}
            <div
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg mt-0.5 ${eventIconColor(ev.event_type)}`}
              aria-hidden="true"
            >
              <Calendar className="h-3 w-3" />
            </div>

            {/* Content card */}
            <div className="flex-1 bg-muted/30 rounded-xl border border-border/40 px-4 py-3 mb-1">
              <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                <span
                  className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${eventChipColor(ev.event_type)}`}
                >
                  {formatEventType(ev.event_type)}
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {formatDate(ev.detected_date)}
                </span>
                {ev.source_article_indices.length > 0 && (
                  <span className="text-[11px] text-muted-foreground">
                    · {ev.source_article_indices.length} source
                    {ev.source_article_indices.length !== 1 ? "s" : ""}
                  </span>
                )}
              </div>
              <p className="text-sm text-foreground leading-relaxed">
                {ev.description}
              </p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
