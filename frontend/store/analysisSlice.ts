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

import type { StateCreator } from 'zustand';
import type { StoreState } from './index';
import type {
  StepEvent,
  PipelineCompleteEvent,
  PipelineFailedEvent,
} from '../types/pipeline';
import type {
  CompanyInfo,
  MarketData,
  PriceHistory,
  NewsCollection,
  SentimentResult,
  EventsResult,
  InsightsResult,
  DataSource,
} from '../types/report';

// ─── State shape ─────────────────────────────────────────────────────────────

export interface AnalysisState {
  // Current run identifiers
  runId: string | null;
  ticker: string;
  status: 'idle' | 'loading' | 'streaming' | 'complete' | 'failed' | 'timeout';

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
  completeness: 'complete' | 'partial' | 'minimal' | null;

  // Error message set on failure
  errorMessage: string | null;

  // Actions
  startAnalysis: (ticker: string) => void;
  appendStepEvent: (event: StepEvent) => void;
  setPipelineComplete: (event: PipelineCompleteEvent) => void;
  setPipelineFailed: (event: Pick<PipelineFailedEvent, 'reason'> & Partial<PipelineFailedEvent>) => void;
  reset: () => void;
}

// ─── Initial state ────────────────────────────────────────────────────────────

const initialAnalysisState = {
  runId: null,
  ticker: '',
  status: 'idle' as const,
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
      status: 'loading',
    }),

  /**
   * Appends a step event in arrival order.
   * Transitions status to 'streaming' on the first event.
   */
  appendStepEvent: (event: StepEvent) =>
    set((state) => ({
      stepEvents: [...state.stepEvents, event],
      status: state.status === 'loading' ? 'streaming' : state.status,
    })),

  /**
   * Called when the pipeline_complete SSE event arrives.
   * Populates all report section fields from the event payload.
   */
  setPipelineComplete: (event: PipelineCompleteEvent) =>
    set({
      status: 'complete',
      runId: event.run_id,
      company: event.report.company,
      marketData: event.report.market_data,
      priceHistory: event.report.price_history,
      news: event.report.news,
      sentiment: event.report.sentiment,
      events: event.report.events,
      insights: event.report.insights,
      dataSources: event.report.data_sources,
      partialDataNotices: event.report.partial_data_notices,
      errorNotices: event.report.error_notices,
      completeness: event.completeness,
      errorMessage: null,
    }),

  /**
   * Called when the pipeline_failed or pipeline_timeout event arrives,
   * or when the POST /analyze call fails.
   */
  setPipelineFailed: (event) =>
    set({
      status: 'failed',
      errorMessage: event.reason,
    }),

  /**
   * Resets the entire slice to initial values.
   * Explicitly sets runId: null and stepEvents: [] per acceptance criteria.
   */
  reset: () => set({ ...initialAnalysisState }),
});
