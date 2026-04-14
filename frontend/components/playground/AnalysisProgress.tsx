"use client";

/**
 * AnalysisProgress — compact pipeline progress tracker.
 *
 * Collapsed: a minimal text strip with inline micro progress bar.
 *            Resembles a "thinking" block — no heavy card chrome.
 * Expanded:  clean step timeline with left-border accent on the active step,
 *            pop animations on recently-completed steps.
 *
 * Auto-expands when analysis starts; auto-collapses when complete or failed.
 */

import { useEffect, useRef, useState } from "react";
import {
  CheckCircle2,
  XCircle,
  Loader2,
  SkipForward,
  Clock,
  ChevronDown,
} from "lucide-react";
import { useAnalysisStore, useUIStore } from "@/store";
import type { StepName, StepStatus } from "@/types/pipeline";

// ─── Step metadata ────────────────────────────────────────────────────────────

type StepMeta = {
  name: StepName;
  label: string;
  description: string;
};

export const ALL_STEPS: StepMeta[] = [
  {
    name: "ticker_validation",
    label: "Validating ticker",
    description: "Resolving company information",
  },
  {
    name: "market_data_collection",
    label: "Fetching market data",
    description: "Price, volume, financial ratios",
  },
  {
    name: "news_retrieval",
    label: "Retrieving news",
    description: "Recent articles from news sources",
  },
  {
    name: "news_deduplication",
    label: "Deduplicating articles",
    description: "Removing duplicate coverage",
  },
  {
    name: "article_summarization",
    label: "Summarizing articles",
    description: "AI-powered article summaries",
  },
  {
    name: "sentiment_classification",
    label: "Classifying sentiment",
    description: "Positive / neutral / negative scoring",
  },
  {
    name: "event_extraction",
    label: "Extracting events",
    description: "Key business events from news",
  },
  {
    name: "insight_generation",
    label: "Generating insights",
    description: "AI research overview",
  },
  {
    name: "report_assembly",
    label: "Assembling report",
    description: "Compiling the final report",
  },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getStepStatus(
  stepName: StepName,
  stepEvents: { step: StepName; status: StepStatus }[],
  pipelineStatus: string,
  activeIndex: number,
  thisIndex: number,
): "pending" | "running" | "completed" | "failed" | "skipped" {
  const event = stepEvents.find((e) => e.step === stepName);

  if (event) {
    if (event.status === "started") return "running";
    else return event.status;
  }

  if (thisIndex < activeIndex) return "completed";
  if (thisIndex === activeIndex && pipelineStatus === "streaming")
    return "running";

  return "pending";
}

// ─── Step icon ────────────────────────────────────────────────────────────────

function StepIcon({ state }: { state: ReturnType<typeof getStepStatus> }) {
  const cls = "h-3.5 w-3.5 shrink-0";
  switch (state) {
    case "completed":
      return (
        <CheckCircle2
          className={`${cls} text-emerald-500`}
          aria-hidden="true"
        />
      );
    case "failed":
      return <XCircle className={`${cls} text-red-500`} aria-hidden="true" />;
    case "skipped":
      return (
        <SkipForward
          className={`${cls} text-muted-foreground`}
          aria-hidden="true"
        />
      );
    case "running":
      return (
        <Loader2
          className={`${cls} text-brand-500 animate-spin`}
          aria-hidden="true"
        />
      );
    default:
      return (
        <Clock
          className={`${cls} text-muted-foreground opacity-30`}
          aria-hidden="true"
        />
      );
  }
}

// ─── Step row ─────────────────────────────────────────────────────────────────

type StepRowProps = {
  step: StepMeta;
  index: number;
  isLast: boolean;
  stepEvents: { step: StepName; status: StepStatus }[];
  status: string;
  activeIndex: number;
};

function StepRow({
  step,
  index,
  isLast,
  stepEvents,
  status,
  activeIndex,
}: StepRowProps) {
  const state = getStepStatus(
    step.name,
    stepEvents,
    status,
    activeIndex,
    index,
  );
  const isActiveStep = state === "running";

  const completedAtRef = useRef<number | null>(null);
  if (state === "completed" && completedAtRef.current === null) {
    completedAtRef.current = Date.now();
  }

  const [isRecentlyCompleted, setIsRecentlyCompleted] = useState(false);

  useEffect(() => {
    if (state === "completed" && completedAtRef.current !== null) {
      const age = Date.now() - completedAtRef.current;
      if (age < 800) {
        setIsRecentlyCompleted(true);
        const t = setTimeout(() => setIsRecentlyCompleted(false), 800 - age);
        return () => clearTimeout(t);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state]);

  return (
    <li className="flex items-stretch gap-2.5">
      {/* Left gutter: icon + connector line */}
      <div className="flex flex-col items-center">
        <div
          className={`mt-1.5 ${
            isRecentlyCompleted
              ? "animate-step-complete"
              : isActiveStep
                ? "animate-step-pop"
                : ""
          }`}
        >
          <StepIcon state={state} />
        </div>
        {!isLast && (
          <div
            className={`w-px flex-1 my-0.5 transition-colors duration-300 ${
              state === "completed" || state === "skipped"
                ? "bg-emerald-400/40"
                : "bg-border"
            }`}
            style={{ minHeight: "10px" }}
          />
        )}
      </div>

      {/* Step content */}
      <div
        className={`flex-1 flex flex-col justify-center py-0.5 transition-all duration-200 ${
          isActiveStep ? "border-l-2 border-brand-500 pl-2 -ml-px" : "pl-0"
        }`}
      >
        <span
          className={`text-xs font-medium leading-tight transition-colors duration-200 ${
            state === "completed"
              ? "text-foreground"
              : state === "running"
                ? "text-brand-600 dark:text-brand-400"
                : state === "failed"
                  ? "text-red-600 dark:text-red-400"
                  : state === "skipped"
                    ? "text-muted-foreground"
                    : "text-muted-foreground opacity-40"
          }`}
        >
          {step.label}
        </span>
        {isActiveStep && (
          <span className="text-[10px] text-muted-foreground mt-0.5 animate-fade-in-up">
            {step.description}
          </span>
        )}
      </div>
    </li>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

export function AnalysisProgress() {
  const { stepEvents, status, ticker } = useAnalysisStore();
  const { progressExpanded, toggleProgressExpanded, setProgressExpanded } =
    useUIStore();

  const completedCount = stepEvents.filter(
    (e) => e.status === "completed" || e.status === "skipped",
  ).length;
  const totalSteps = ALL_STEPS.length;
  const progressPct = Math.round((completedCount / totalSteps) * 100);

  const runningEvent = stepEvents.find((e) => e.status === "started");
  const runningStepName = runningEvent?.step;
  const activeIndex = runningStepName
    ? ALL_STEPS.findIndex((s) => s.name === runningStepName)
    : completedCount;

  const runningStepMeta = ALL_STEPS.find((s) => s.name === runningStepName);

  const isComplete = status === "complete";
  const isFailed = status === "failed" || status === "timeout";
  const isRunning = status === "loading" || status === "streaming";

  // Auto-expand on start, auto-collapse on completion or failure.
  useEffect(() => {
    if (status === "loading" || status === "streaming") {
      setProgressExpanded(true);
    }
    if (status === "complete") {
      const t = setTimeout(() => setProgressExpanded(false), 800);
      return () => clearTimeout(t);
    }
    if (status === "failed" || status === "timeout") {
      // Keep expanded for 2s so user sees the failed step, then collapse.
      const t = setTimeout(() => setProgressExpanded(false), 2000);
      return () => clearTimeout(t);
    }
  }, [status, setProgressExpanded]);

  const headerStatusText = (() => {
    if (isComplete) return `All ${totalSteps} steps completed`;
    if (isFailed) return "Analysis failed";

    if (runningStepMeta) {
      return `${runningStepMeta.label}…`;
    }

    if (status === "loading") {
      return `Starting analysis for ${ticker}…`;
    }

    return `Analyzing ${ticker}`;
  })();

  const collapsedSubtext = isComplete
    ? `${totalSteps} of ${totalSteps} steps completed`
    : isFailed
      ? "Pipeline stopped"
      : `${completedCount} of ${totalSteps} steps`;

  return (
    <div className="w-full" aria-label="Analysis pipeline progress">
      {/* ── Inline header strip (always visible) ────────────────────────── */}
      <div className="flex items-center gap-2.5 py-2">
        {/* Status icon — no badge background, just the icon */}
        {isRunning ? (
          <Loader2
            className="h-3.5 w-3.5 text-brand-500 animate-spin shrink-0"
            aria-hidden="true"
          />
        ) : isComplete ? (
          <CheckCircle2
            className="h-3.5 w-3.5 text-emerald-500 shrink-0"
            aria-hidden="true"
          />
        ) : isFailed ? (
          <XCircle
            className="h-3.5 w-3.5 text-red-500 shrink-0"
            aria-hidden="true"
          />
        ) : (
          <Clock
            className="h-3.5 w-3.5 text-muted-foreground opacity-40 shrink-0"
            aria-hidden="true"
          />
        )}

        {/* Status text */}
        <span className="text-xs text-muted-foreground flex-1 truncate min-w-0">
          {progressExpanded ? collapsedSubtext : headerStatusText}
        </span>

        {/* Inline micro progress bar */}
        <div className="w-20 h-1 rounded-full bg-muted overflow-hidden shrink-0">
          {isRunning && progressPct === 0 ? (
            <div className="h-full w-1/3 bg-brand-500 opacity-70 animate-progress-indeterminate" />
          ) : (
            <div
              className={`h-full rounded-full transition-all duration-500 ease-out ${
                isFailed
                  ? "bg-red-400"
                  : isComplete
                    ? "bg-emerald-500"
                    : "bg-brand-500"
              }`}
              style={{ width: `${isComplete ? 100 : progressPct}%` }}
              role="progressbar"
              aria-valuenow={isComplete ? 100 : progressPct}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label={`Analysis progress: ${isComplete ? 100 : progressPct}%`}
            />
          )}
        </div>

        {/* Percentage */}
        <span className="text-[10px] font-mono tabular-nums text-muted-foreground w-7 text-right shrink-0">
          {isComplete ? "100%" : `${progressPct}%`}
        </span>

        {/* Expand toggle */}
        <button
          onClick={toggleProgressExpanded}
          className="ml-0.5 p-0.5 rounded text-muted-foreground hover:text-foreground transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-brand-500"
          aria-expanded={progressExpanded}
          aria-controls="progress-steps"
          aria-label={
            progressExpanded
              ? "Collapse pipeline steps"
              : "Expand pipeline steps"
          }
        >
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform duration-200 ${progressExpanded ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>
      </div>

      {/* ── Expandable step timeline ─────────────────────────────────────── */}
      {progressExpanded && (
        <div id="progress-steps" className="ml-1 mt-0.5 pb-2">
          <ol className="space-y-0" aria-label="Pipeline steps">
            {ALL_STEPS.map((step, index) => (
              <StepRow
                key={step.name}
                step={step}
                index={index}
                isLast={index === ALL_STEPS.length - 1}
                stepEvents={stepEvents}
                status={status}
                activeIndex={activeIndex}
              />
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
