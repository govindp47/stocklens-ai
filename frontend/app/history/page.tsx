"use client";

/**
 * /history — list of past analysis runs fetched from the backend API.
 * Groups runs by date and displays them as a rich timeline.
 * Clicking a row navigates to the full /analysis/[runId] report page.
 */

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { formatDistanceToNow } from "@/lib/formatters";
import { getCompletedRuns, ApiError } from "@/lib/api";
import type { RunSummary } from "@/types/report";
import {
  History,
  ArrowRight,
  TrendingUp,
  SearchX,
  AlertCircle,
  Clock,
  Cpu,
} from "lucide-react";
import { useHistoryStore } from "@/store/historySlice";

// ─── Duration formatter ───────────────────────────────────────────────────────

function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

// ─── Date group label ─────────────────────────────────────────────────────────

function getGroupLabel(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();

  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  );
  const startOfYesterday = new Date(startOfToday.getTime() - 86_400_000);
  const startOfWeek = new Date(
    startOfToday.getTime() - startOfToday.getDay() * 86_400_000,
  );

  if (date >= startOfToday) return "Today";
  if (date >= startOfYesterday) return "Yesterday";
  if (date >= startOfWeek)
    return date.toLocaleDateString("en-US", { weekday: "long" });

  return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

// ─── Completeness left-border color ──────────────────────────────────────────

function completenessAccent(completeness: string): string {
  switch (completeness) {
    case "complete":
      return "border-l-2 border-emerald-400 dark:border-emerald-500";
    case "partial":
      return "border-l-2 border-amber-400 dark:border-amber-500";
    default:
      return "border-l-2 border-red-400 dark:border-red-500";
  }
}

// ─── LLM provider badge ───────────────────────────────────────────────────────

function ProviderBadge({
  provider,
  model,
}: {
  provider: string;
  model: string | null;
}) {
  const isOpenAi = provider === "openai";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold
        ${
          isOpenAi
            ? "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950/30 dark:text-violet-400 dark:border-violet-800/50"
            : "bg-brand-50 text-brand-700 border-brand-200 dark:bg-brand-50/10 dark:text-brand-400 dark:border-brand-700/50"
        }`}
    >
      <Cpu className="h-2.5 w-2.5" aria-hidden="true" />
      {model ?? provider}
    </span>
  );
}

// ─── Skeleton row ─────────────────────────────────────────────────────────────

function HistorySkeletonRow() {
  return (
    <div className="flex gap-4 items-start py-3 px-4 rounded-2xl border border-border bg-surface">
      <div className="h-10 w-10 shrink-0 rounded-xl animate-shimmer" />
      <div className="flex-1 space-y-2 pt-0.5">
        <div className="flex items-center gap-2">
          <div className="h-5 w-20 rounded-md animate-shimmer" />
          <div className="h-4 w-24 rounded-full animate-shimmer" />
        </div>
        <div className="h-3 w-36 rounded-full animate-shimmer" />
        <div className="h-3 w-28 rounded-full animate-shimmer" />
      </div>
      <div className="h-4 w-4 rounded animate-shimmer shrink-0 mt-1" />
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function HistoryPage() {
  const router = useRouter();
  const { entries: historyEntries } = useHistoryStore();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Build a quick-lookup map from run_id → local history entry (has company name + completeness)
  const historyMap = useMemo(() => {
    const map = new Map<
      string,
      { companyName?: string; completeness: string }
    >();
    historyEntries.forEach((e) =>
      map.set(e.runId, {
        companyName: e.companyName,
        completeness: e.completeness,
      }),
    );
    return map;
  }, [historyEntries]);

  useEffect(() => {
    let cancelled = false;

    getCompletedRuns(50, 0)
      .then((data) => {
        if (!cancelled) setRuns(data.runs);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError ? err.message : "Failed to load history.",
          );
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Group runs by date bucket
  const grouped = useMemo(() => {
    const groups: { label: string; runs: RunSummary[] }[] = [];
    const indexMap = new Map<string, number>();
    runs.forEach((run) => {
      const label = getGroupLabel(run.completed_at);
      if (!indexMap.has(label)) {
        indexMap.set(label, groups.length);
        groups.push({ label, runs: [] });
      }
      groups[indexMap.get(label)!].runs.push(run);
    });
    return groups;
  }, [runs]);

  function retryLoad() {
    setError(null);
    setLoading(true);
    getCompletedRuns(50, 0)
      .then((d) => setRuns(d.runs))
      .catch((e: unknown) =>
        setError(e instanceof ApiError ? e.message : "Failed to load history."),
      )
      .finally(() => setLoading(false));
  }

  return (
    <div className="mx-auto max-w-3xl px-4 sm:px-6 py-8">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 ring-1 ring-brand-200/50 dark:bg-brand-50/10 dark:ring-brand-700/30">
            <History className="h-5 w-5 text-brand-500" aria-hidden="true" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground tracking-tight flex items-baseline gap-2">
              Past Analyses
              {!loading && !error && runs.length > 0 && (
                <span className="text-sm font-normal text-muted-foreground">
                  ({runs.length})
                </span>
              )}
            </h1>
            <p className="text-xs text-muted-foreground mt-0.5">
              {loading
                ? "Loading…"
                : error
                  ? "Could not load runs"
                  : runs.length > 0
                    ? `${runs.length} completed run${runs.length === 1 ? "" : "s"}`
                    : "No analyses yet"}
            </p>
          </div>
        </div>
      </div>

      {/* ── Loading skeleton ─────────────────────────────────────────────── */}
      {loading && (
        <div
          className="space-y-2"
          aria-label="Loading past analyses"
          aria-busy="true"
        >
          {[...Array(5)].map((_, i) => (
            <HistorySkeletonRow key={i} />
          ))}
        </div>
      )}

      {/* ── Error state ──────────────────────────────────────────────────── */}
      {!loading && error && (
        <div className="flex flex-col items-center gap-4 rounded-2xl border border-red-200/70 bg-red-50/60 py-12 px-6 text-center dark:border-red-800/30 dark:bg-red-950/20">
          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-red-100 dark:bg-red-950/40">
            <AlertCircle className="h-6 w-6 text-red-500" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold text-red-700 dark:text-red-400">
              Failed to load history
            </p>
            <p className="text-xs text-red-500/80 dark:text-red-500 mt-1">
              {error}
            </p>
          </div>
          <button
            onClick={retryLoad}
            className="inline-flex items-center gap-2 rounded-xl border border-red-200 bg-surface px-4 py-2.5 text-xs font-semibold text-red-700
              hover:bg-red-50 transition-colors focus:outline-none focus:ring-2 focus:ring-red-400 dark:border-red-800/50 dark:text-red-400"
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Empty state ───────────────────────────────────────────────────── */}
      {!loading && !error && runs.length === 0 && (
        <div className="flex flex-col items-center gap-5 rounded-2xl border border-border bg-surface py-16 px-6 text-center shadow-panel">
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-muted">
            <SearchX
              className="h-7 w-7 text-muted-foreground"
              aria-hidden="true"
            />
          </div>
          <div>
            <p className="text-base font-semibold text-foreground">
              No analyses yet
            </p>
            <p className="text-sm text-muted-foreground mt-1.5 max-w-xs leading-relaxed">
              Search for a ticker on the Analyze page to get started. Your
              completed reports will appear here.
            </p>
          </div>
          <button
            onClick={() => router.push("/")}
            className="inline-flex items-center gap-2 rounded-xl bg-brand-500 px-5 py-2.5 text-sm font-semibold text-white
              hover:bg-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 transition-colors"
          >
            <TrendingUp className="h-4 w-4" aria-hidden="true" />
            Analyze a ticker
          </button>
        </div>
      )}

      {/* ── Grouped runs timeline ────────────────────────────────────────── */}
      {!loading && !error && grouped.length > 0 && (
        <div>
          {grouped.map((group) => (
            <div key={group.label}>
              {/* Date group header */}
              <div className="flex items-center gap-3 mb-2 mt-6 first:mt-0">
                <span className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground whitespace-nowrap">
                  {group.label}
                </span>
                <div className="flex-1 h-px bg-border/50" />
              </div>

              {/* Runs in this group */}
              <ol
                className="space-y-2"
                aria-label={`Analyses from ${group.label}`}
              >
                {group.runs.map((run) => (
                  <li key={run.run_id}>
                    {(() => {
                      const local = historyMap.get(run.run_id);
                      const completeness = local?.completeness ?? "minimal";
                      const companyName = local?.companyName;
                      return (
                        <button
                          onClick={() => router.push(`/analysis/${run.run_id}`)}
                          className={`group w-full rounded-2xl border border-border bg-surface px-5 py-4 text-left
                            hover:border-brand-200/60 hover:bg-muted/20 hover:shadow-panel-hover
                            focus:outline-none focus:ring-2 focus:ring-brand-500 transition-all duration-150 shadow-panel
                            ${completenessAccent(completeness)}`}
                        >
                          <div className="flex items-center justify-between gap-4">
                            {/* Left: icon + meta */}
                            <div className="flex items-center gap-4 min-w-0">
                              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brand-50 ring-1 ring-brand-200/40 dark:bg-brand-50/10 dark:ring-brand-700/20">
                                <TrendingUp
                                  className="h-4 w-4 text-brand-500"
                                  aria-hidden="true"
                                />
                              </div>
                              <div className="min-w-0">
                                {/* Row 1: ticker + provider badge */}
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="font-mono text-base font-bold tracking-tight text-foreground">
                                    {run.ticker}
                                  </span>
                                  <ProviderBadge
                                    provider={run.llm_provider}
                                    model={run.llm_model}
                                  />
                                </div>
                                {/* Row 2: company name if available in local history */}
                                {companyName && (
                                  <p className="text-xs text-muted-foreground mt-0.5 truncate">
                                    {companyName}
                                  </p>
                                )}
                                {/* Row 3: time · duration · steps */}
                                <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground flex-wrap">
                                  <span className="flex items-center gap-1">
                                    <Clock
                                      className="h-3 w-3"
                                      aria-hidden="true"
                                    />
                                    {formatDistanceToNow(run.completed_at)}
                                  </span>
                                  <span
                                    aria-hidden="true"
                                    className="text-border"
                                  >
                                    ·
                                  </span>
                                  <span>{formatDuration(run.duration_ms)}</span>
                                  <span
                                    aria-hidden="true"
                                    className="text-border"
                                  >
                                    ·
                                  </span>
                                  <span className="tabular-nums">
                                    {run.steps_completed}/{run.steps_total}{" "}
                                    steps
                                  </span>
                                </div>
                              </div>
                            </div>

                            {/* Right: arrow */}
                            <ArrowRight
                              className="h-4 w-4 text-muted-foreground/50 shrink-0 transition-all duration-150 group-hover:text-brand-500 group-hover:translate-x-0.5"
                              aria-hidden="true"
                            />
                          </div>
                        </button>
                      );
                    })()}
                  </li>
                ))}
              </ol>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
