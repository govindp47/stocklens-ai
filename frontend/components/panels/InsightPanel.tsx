"use client";

/**
 * InsightPanel — AI-generated research overview divided into six named sections.
 */

import {
  Sparkles,
  Building2,
  Newspaper,
  BarChart2,
  TrendingUp,
  ShieldAlert,
  BrainCircuit,
} from "lucide-react";
import { useAnalysisStore } from "@/store";
import { Panel } from "@/components/ui/Panel";
import { PanelSkeleton } from "@/components/ui/PanelSkeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { DISCLAIMER_TEXT } from "@/lib/constants";
import type { InsightSections } from "@/types/report";

const INSUFFICIENT_DATA_SENTINEL =
  "Insufficient data available for this section";

const SECTION_ORDER: Array<{
  key: keyof InsightSections;
  label: string;
  icon: React.ElementType;
}> = [
  { key: "company_overview", label: "Company Overview", icon: Building2 },
  { key: "recent_developments", label: "Recent Developments", icon: Newspaper },
  { key: "sentiment_overview", label: "Sentiment Overview", icon: BarChart2 },
  { key: "potential_drivers", label: "Potential Drivers", icon: TrendingUp },
  { key: "potential_risks", label: "Potential Risks", icon: ShieldAlert },
  { key: "ai_summary", label: "AI Summary", icon: BrainCircuit },
];

function InsightSection({
  label,
  content,
  icon: Icon,
}: {
  label: string;
  content: string;
  icon: React.ElementType;
}) {
  const isInsufficient = content.includes(INSUFFICIENT_DATA_SENTINEL);

  return (
    <div className="border-b border-border/40 last:border-0 px-5 py-4">
      <h3 className="flex items-center gap-2 text-xs font-semibold text-foreground mb-2.5 uppercase tracking-wide">
        <Icon
          className="h-3.5 w-3.5 text-brand-500 shrink-0"
          aria-hidden="true"
        />
        {label}
      </h3>
      <p
        className={`text-sm leading-relaxed ${
          isInsufficient
            ? "text-muted-foreground/60 italic"
            : "text-muted-foreground"
        }`}
      >
        {isInsufficient
          ? "Not enough data available for this section."
          : content}
      </p>
    </div>
  );
}

export function InsightPanel() {
  const { insights, status } = useAnalysisStore();

  const panelStatus = (() => {
    if (!insights) return "loading";
    if (!insights.available) return "unavailable";
    return "populated";
  })();

  const isLoading =
    !insights && (status === "loading" || status === "streaming");

  const aiBadge = (
    <span className="inline-flex items-center gap-1 rounded-full border border-brand-200/60 bg-brand-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-brand-600 dark:bg-brand-50/10 dark:border-brand-700/40 dark:text-brand-400">
      <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />
      AI
    </span>
  );

  return (
    <Panel
      id="insights"
      title="AI Research Overview"
      status={panelStatus}
      badge={aiBadge}
    >
      {isLoading ? (
        <PanelSkeleton rows={8} />
      ) : !insights || !insights.available || !insights.sections ? (
        <ErrorState message="AI insights could not be generated. Other data is still available." />
      ) : (
        <div>
          {SECTION_ORDER.map(({ key, label, icon }) => (
            <InsightSection
              key={key}
              label={label}
              icon={icon}
              content={insights.sections![key] || INSUFFICIENT_DATA_SENTINEL}
            />
          ))}
          <div
            role="note"
            className="mx-5 mb-5 mt-2 rounded-xl border border-border/50 bg-accent/60 px-4 py-3 text-[11px] text-muted-foreground leading-relaxed"
            data-testid="insight-disclaimer"
          >
            {insights.disclaimer || DISCLAIMER_TEXT}
          </div>
        </div>
      )}
    </Panel>
  );
}
