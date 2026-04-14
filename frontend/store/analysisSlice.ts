/**
 * analysisSlice — tracks the current pipeline run state and all SSE step events.
 *
 * Design notes:
 * - stepEvents is append-only; insertion order is always preserved.
 * - Panel data (company, marketData, …) is populated by setPipelineComplete.
 * - appendStepEvent updates status to 'streaming' on first event and records
 *   per-step progress for the ReasoningViewer component.
 * - reset() returns every field to its initial value, including runId: null.
 */

import type { StateCreator } from "zustand";
import type { StoreState } from "./index";
import type {
  StepEvent,
  PipelineCompleteEvent,
  PipelineFailedEvent,
} from "../types/pipeline";
import type {
  CompanyInfo,
  MarketData,
  PriceHistory,
  NewsCollection,
  SentimentResult,
  EventsResult,
  InsightsResult,
  DataSource,
} from "../types/report";

// ─── State shape ─────────────────────────────────────────────────────────────

export interface AnalysisState {
  // Current run identifiers
  runId: string | null;
  ticker: string;
  status: "idle" | "loading" | "streaming" | "complete" | "failed" | "timeout";

  // Step events — append-only as SSE frames arrive
  stepEvents: StepEvent[];

  // Derived panel data (populated by setPipelineComplete)
  company: CompanyInfo | null;
  marketData: MarketData | null;
  priceHistory: PriceHistory | null;
  news: NewsCollection | null;
  sentiment: SentimentResult | null;
  events: EventsResult | null;
  insights: InsightsResult | null;
  dataSources: DataSource[];

  // Partial report indicators
  partialDataNotices: string[];
  errorNotices: string[];
  completeness: "complete" | "partial" | "minimal" | null;

  // Error message set on failure
  errorMessage: string | null;

  // Actions
  startAnalysis: (ticker: string) => void;
  setRunId: (runId: string) => void;
  appendStepEvent: (event: StepEvent) => void;
  setPipelineComplete: (event: PipelineCompleteEvent) => void;
  setPipelineFailed: (
    event: Pick<PipelineFailedEvent, "reason"> & Partial<PipelineFailedEvent>,
  ) => void;
  reset: () => void;
}

// ─── Initial state ────────────────────────────────────────────────────────────

const initialAnalysisState = {
  runId: null,
  ticker: "",
  status: "idle" as const,
  stepEvents: [],
  company: null,
  marketData: null,
  priceHistory: null,
  news: null,
  sentiment: null,
  events: null,
  insights: null,
  dataSources: [],
  partialDataNotices: [],
  errorNotices: [],
  completeness: null,
  errorMessage: null,
};

// ─── Slice factory ────────────────────────────────────────────────────────────

export const createAnalysisSlice: StateCreator<
  StoreState,
  [],
  [],
  AnalysisState
> = (set) => ({
  ...initialAnalysisState,

  /**
   * Called immediately when the user submits a ticker.
   * Clears all previous run data and sets status to 'loading'.
   */
  startAnalysis: (ticker: string) =>
    set({
      ...initialAnalysisState,
      ticker: ticker.toUpperCase().trim(),
      status: "loading",
    }),

  setRunId: (runId: string) => set({ runId }),

  /**
   * Upserts a step event by step name.
   * The backend emits two events per step (status="started" then "completed"/
   * "failed"/"skipped"), so we update an existing entry rather than append a
   * duplicate.
   * Transitions status to 'streaming' on the first event.
   */
  appendStepEvent: (event: any) =>
    set((state) => {
      const normalized: StepEvent = {
        event_type: "step_event",
        run_id: event.run_id,
        step: event.step ?? event.step_name,
        status: event.status,
        timestamp: event.timestamp,
        data: event.data,
      };

      const existingIndex = state.stepEvents.findIndex(
        (e) => e.step === normalized.step,
      );

      let stepEvents: StepEvent[];

      if (existingIndex >= 0) {
        stepEvents = state.stepEvents.map((e, i) =>
          i === existingIndex ? normalized : e,
        );
      } else {
        stepEvents = [...state.stepEvents, normalized];
      }

      return {
        stepEvents,
        status: state.status === "loading" ? "streaming" : state.status,
      };
    }),

  /**
   * Called when the pipeline_complete SSE event arrives.
   * Populates all report section fields from the event payload.
   */
  setPipelineComplete: (event: PipelineCompleteEvent) => {
    const report = event.report;
    if (!report) {
      // Should not happen in practice; guard defensively.
      set({ status: "failed", errorMessage: "Report data was empty." });
      return;
    }
    set({
      status: "complete",
      runId: event.run_id,
      company: report.company,
      marketData: report.market_data,
      priceHistory: report.price_history,
      news: report.news,
      sentiment: report.sentiment,
      events: report.events,
      insights: report.insights,
      dataSources: report.data_sources,
      partialDataNotices: report.partial_data_notices,
      errorNotices: report.error_notices,
      completeness: event.completeness,
      errorMessage: null,
    });
  },

  /**
   * Called when the pipeline_failed or pipeline_timeout event arrives,
   * or when the POST /analyze call fails.
   */
  setPipelineFailed: (event) =>
    set({
      status: "failed",
      errorMessage: event.reason,
    }),

  /**
   * Resets the entire slice to initial values.
   * Explicitly sets runId: null and stepEvents: [] per acceptance criteria.
   */
  reset: () => set({ ...initialAnalysisState }),
});
