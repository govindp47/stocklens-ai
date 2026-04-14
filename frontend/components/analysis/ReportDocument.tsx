"use client";

/**
 * ReportDocument — full-page professional analysis report.
 *
 * Layout (responsive grid, not accordion panels):
 *  Row 1 — Report header (full width)
 *  Row 2 — Market snapshot (2/3) + Sentiment (1/3) side-by-side
 *  Row 3 — Price chart (full width, prominent)
 *  Row 4 — AI Insights (1/2) + Key Events (1/2) side-by-side
 *  Row 5 — News feed (full width, editorial style)
 *  Row 6 — Data sources + notices (1/2 each)
 *
 * Used on the /analysis/[runId] page.
 */

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useAnalysis } from "@/hooks/useAnalysis";
import type { AnalysisReport } from "@/types/report";
import { MarketSnapshot } from "./MarketSnapshot";
import { SentimentSummary } from "./SentimentSummary";
import { EventTimeline } from "./EventTimeline";
import { NewsArticleList } from "./NewsArticleList";
import { formatDateTime } from "@/lib/formatters";
import {
  RotateCcw,
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  TrendingUp,
  BarChart2,
  Newspaper,
  CalendarDays,
  BrainCircuit,
  Database,
} from "lucide-react";
import { useState } from "react";

const PriceTrendChartClient = dynamic(
  () => import("@/components/panels/PriceTrendChartClient"),
  { ssr: false },
);

// ─── Timeframe filter ─────────────────────────────────────────────────────────

type Timeframe = "1M" | "3M";

function filterByTimeframe<T extends { date: string }>(
  datapoints: T[],
  tf: Timeframe,
): T[] {
  const now = new Date();
  const cutoff = new Date(now);
  if (tf === "1M") cutoff.setMonth(now.getMonth() - 1);
  else cutoff.setMonth(now.getMonth() - 3);
  return datapoints.filter((p) => new Date(p.date) >= cutoff);
}

// ─── Shared card primitives ───────────────────────────────────────────────────

function ReportCard({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-2xl border border-border bg-surface shadow-panel dark:shadow-glow-border
        hover:shadow-panel-hover transition-shadow duration-200 overflow-hidden ${className ?? ""}`}
    >
      {children}
    </div>
  );
}

function CardHeader({
  icon: Icon,
  title,
  badge,
}: {
  icon: React.ElementType;
  title: string;
  badge?: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-3 px-5 pt-4 pb-3 border-b border-border/50">
      <Icon className="h-4 w-4 text-brand-500 shrink-0" aria-hidden="true" />
      <h2 className="text-sm font-semibold text-foreground tracking-tight flex-1">
        {title}
      </h2>
      {badge}
    </div>
  );
}

// ─── Completeness badge ───────────────────────────────────────────────────────

function CompletenessBadge({
  value,
}: {
  value: AnalysisReport["completeness"];
}) {
  const map = {
    complete: {
      label: "Complete",
      icon: CheckCircle2,
      cls: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-800/50",
    },
    partial: {
      label: "Partial",
      icon: AlertTriangle,
      cls: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-800/50",
    },
    minimal: {
      label: "Minimal",
      icon: AlertCircle,
      cls: "bg-red-50 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-400 dark:border-red-800/50",
    },
  };
  const { label, icon: Icon, cls } = map[value];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-semibold ${cls}`}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {label}
    </span>
  );
}

// ─── Insight sections ─────────────────────────────────────────────────────────

const INSIGHT_SECTIONS: {
  key: keyof NonNullable<AnalysisReport["insights"]["sections"]>;
  label: string;
  color: string;
}[] = [
  {
    key: "company_overview",
    label: "Company Overview",
    color: "border-brand-200 dark:border-brand-700",
  },
  {
    key: "recent_developments",
    label: "Recent Developments",
    color: "border-sky-200 dark:border-sky-700",
  },
  {
    key: "sentiment_overview",
    label: "Sentiment Overview",
    color: "border-amber-200 dark:border-amber-700",
  },
  {
    key: "potential_drivers",
    label: "Potential Drivers",
    color: "border-emerald-200 dark:border-emerald-700",
  },
  {
    key: "potential_risks",
    label: "Potential Risks",
    color: "border-red-200 dark:border-red-700",
  },
  {
    key: "ai_summary",
    label: "AI Summary",
    color: "border-violet-200 dark:border-violet-700",
  },
];

// ─── Main component ───────────────────────────────────────────────────────────

export function ReportDocument({ report }: { report: AnalysisReport }) {
  const router = useRouter();
  const { analyze } = useAnalysis();
  const [timeframe, setTimeframe] = useState<Timeframe>("3M");

  const chartData = report.price_history?.available
    ? filterByTimeframe(report.price_history.datapoints, timeframe)
    : [];

  async function handleReanalyze() {
    router.push("/");
    setTimeout(() => analyze(report.ticker), 100);
  }

  return (
    <div className="space-y-5">
      {/* ── Row 1: Report header — full width ──────────────────────────── */}
      <ReportCard>
        {/* Brand accent bar */}
        <div
          className="h-1 bg-gradient-to-r from-brand-500 via-brand-400 to-brand-600"
          aria-hidden="true"
        />
        <div className="px-6 py-6">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-5">
            {/* Identity */}
            <div className="flex items-start gap-4">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-50 to-brand-100 border border-brand-200/60 dark:from-brand-50/10 dark:to-brand-100/5 dark:border-brand-700/30">
                <TrendingUp
                  className="h-6 w-6 text-brand-500"
                  aria-hidden="true"
                />
              </div>
              <div>
                <div className="flex items-center gap-2.5 flex-wrap">
                  <span className="font-mono text-3xl font-black tracking-tight text-foreground leading-none">
                    {report.ticker}
                  </span>
                </div>
                {report.company?.name && (
                  <p className="text-base text-foreground mt-1 font-semibold">
                    {report.company.name}
                  </p>
                )}
                {(report.company?.sector || report.company?.industry) && (
                  <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                    {report.company.sector && (
                      <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                        {report.company.sector}
                      </span>
                    )}
                    {report.company.industry && (
                      <span className="inline-flex items-center rounded-full bg-muted px-2.5 py-0.5 text-[11px] font-medium text-muted-foreground">
                        {report.company.industry}
                      </span>
                    )}
                  </div>
                )}
                <p className="text-[11px] text-muted-foreground/70 mt-1.5">
                  Generated {formatDateTime(report.generated_at)}
                </p>
              </div>
            </div>

            {/* Actions + completeness badge */}
            <div className="flex flex-col items-start sm:items-end gap-2.5 shrink-0">
              <CompletenessBadge value={report.completeness} />
              <div className="flex items-center gap-2">
                <button
                  onClick={() => router.back()}
                  className="inline-flex items-center gap-1.5 h-9 rounded-xl border border-border bg-surface px-3 text-xs font-medium text-muted-foreground
                    hover:bg-muted hover:text-foreground focus:outline-none focus:ring-2 focus:ring-brand-500 transition-colors"
                >
                  <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
                  Back
                </button>
                <button
                  onClick={handleReanalyze}
                  className="inline-flex items-center gap-1.5 h-9 rounded-xl bg-brand-500 px-4 text-xs font-semibold text-white
                    hover:bg-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:ring-offset-2 transition-colors"
                >
                  <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                  Re-analyze
                </button>
              </div>
            </div>
          </div>
        </div>
      </ReportCard>

      {/* ── Row 2: Market snapshot (2/3) + Sentiment (1/3) ─────────────── */}
      {(report.market_data?.available || report.sentiment?.available) && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Market snapshot — 2/3 */}
          {report.market_data?.available ? (
            <ReportCard className="lg:col-span-2">
              <CardHeader icon={TrendingUp} title="Market Snapshot" />
              <MarketSnapshot
                marketData={report.market_data}
                company={report.company}
              />
            </ReportCard>
          ) : (
            <div className="lg:col-span-2" />
          )}

          {/* Sentiment — 1/3 */}
          {report.sentiment?.available ? (
            <ReportCard className="lg:col-span-1">
              <CardHeader
                icon={BarChart2}
                title="Sentiment"
                badge={
                  <span className="text-[11px] text-muted-foreground tabular-nums">
                    {report.sentiment.article_count} articles
                  </span>
                }
              />
              <SentimentSummary sentiment={report.sentiment} />
            </ReportCard>
          ) : (
            <div className="lg:col-span-1" />
          )}
        </div>
      )}

      {/* ── Row 3: Price chart — full width, prominent ──────────────────── */}
      {report.price_history?.available && (
        <ReportCard>
          <CardHeader
            icon={BarChart2}
            title="Price History"
            badge={
              <div
                className="flex gap-1"
                role="group"
                aria-label="Select timeframe"
              >
                {(["1M", "3M"] as Timeframe[]).map((tf) => (
                  <button
                    key={tf}
                    onClick={() => setTimeframe(tf)}
                    className={`rounded-lg px-2.5 py-1 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500 ${
                      timeframe === tf
                        ? "bg-brand-500 text-white shadow-xs"
                        : "bg-muted text-muted-foreground hover:text-foreground"
                    }`}
                    aria-pressed={timeframe === tf}
                  >
                    {tf}
                  </button>
                ))}
              </div>
            }
          />
          <div className="h-72 px-2 pb-4 pt-2">
            <PriceTrendChartClient datapoints={chartData} />
          </div>
        </ReportCard>
      )}

      {/* ── Row 4: AI Insights (1/2) + Key Events (1/2) ────────────────── */}
      {(report.insights?.available || report.events?.available) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* AI Research Overview */}
          {report.insights?.available && report.insights.sections && (
            <ReportCard>
              <CardHeader icon={BrainCircuit} title="AI Research Overview" />
              <div className="px-5 pt-4 pb-5 space-y-5">
                {INSIGHT_SECTIONS.map(({ key, label, color }) => {
                  const text = report.insights.sections?.[key];
                  if (!text) return null;
                  return (
                    <div key={key} className={`pl-4 border-l-2 ${color}`}>
                      <h3 className="text-[10px] font-bold uppercase tracking-widest text-brand-500 dark:text-brand-400 mb-1.5">
                        {label}
                      </h3>
                      <p className="text-sm text-muted-foreground leading-relaxed whitespace-pre-line">
                        {text}
                      </p>
                    </div>
                  );
                })}
                {report.insights.disclaimer && (
                  <p className="text-[11px] text-muted-foreground/60 italic border-t border-border pt-4 mt-4 leading-relaxed">
                    {report.insights.disclaimer}
                  </p>
                )}
              </div>
            </ReportCard>
          )}

          {/* Key Events */}
          {report.events?.available && (
            <ReportCard>
              <CardHeader
                icon={CalendarDays}
                title="Key Events"
                badge={
                  <span className="text-[11px] text-muted-foreground tabular-nums">
                    {report.events.events.length} event
                    {report.events.events.length !== 1 ? "s" : ""}
                  </span>
                }
              />
              <EventTimeline events={report.events} />
            </ReportCard>
          )}
        </div>
      )}

      {/* ── Row 5: News feed — full width ───────────────────────────────── */}
      {report.news?.available && (
        <ReportCard>
          <CardHeader
            icon={Newspaper}
            title="Recent News"
            badge={
              <span className="text-[11px] text-muted-foreground tabular-nums">
                {report.news.articles.length} articles
              </span>
            }
          />
          <NewsArticleList news={report.news} />
        </ReportCard>
      )}

      {/* ── Row 6: Data sources + notices ───────────────────────────────── */}
      {(report.data_sources?.length > 0 ||
        report.partial_data_notices?.length > 0) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {/* Data sources */}
          {report.data_sources?.length > 0 && (
            <ReportCard>
              <CardHeader icon={Database} title="Data Sources" />
              <dl className="px-5 pt-3 pb-5 grid grid-cols-1 gap-2.5">
                {report.data_sources.map((ds) => (
                  <div
                    key={ds.name}
                    className="flex items-start gap-3 rounded-xl border border-border bg-muted/30 px-4 py-3"
                  >
                    <div
                      className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                        ds.status === "ok"
                          ? "bg-emerald-500"
                          : ds.status === "partial"
                            ? "bg-amber-400"
                            : "bg-red-400"
                      }`}
                      aria-hidden="true"
                    />
                    <div>
                      <dt className="text-xs font-semibold text-foreground">
                        {ds.name}
                      </dt>
                      <dd className="text-[11px] text-muted-foreground mt-0.5">
                        {ds.detail}
                      </dd>
                    </div>
                  </div>
                ))}
              </dl>
            </ReportCard>
          )}

          {/* Partial data notices */}
          {report.partial_data_notices?.length > 0 && (
            <div className="rounded-2xl border border-amber-200/60 bg-accent px-5 py-4 space-y-2 dark:border-amber-800/30">
              <div className="flex items-center gap-2 mb-3">
                <AlertTriangle
                  className="h-4 w-4 text-amber-600 dark:text-amber-400"
                  aria-hidden="true"
                />
                <span className="text-xs font-semibold text-amber-800 dark:text-accent-foreground">
                  Data Notices
                </span>
              </div>
              {report.partial_data_notices.map((n, i) => (
                <p
                  key={i}
                  className="text-xs text-amber-800 dark:text-accent-foreground leading-relaxed"
                >
                  {n}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
