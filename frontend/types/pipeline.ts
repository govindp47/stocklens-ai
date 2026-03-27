/**
 * SSE pipeline event types — mirrors the backend's event_bus emission shapes.
 */

import type { AnalysisReport } from './report';

// ─── Step names ────────────────────────────────────────────────────────────

export type StepName =
  | 'ticker_validation'
  | 'market_data_collection'
  | 'news_retrieval'
  | 'news_deduplication'
  | 'article_summarization'
  | 'sentiment_classification'
  | 'event_extraction'
  | 'insight_generation'
  | 'report_assembly';

export type StepStatus = 'started' | 'completed' | 'failed' | 'skipped';

// ─── Individual event shapes ────────────────────────────────────────────────

export interface StepEvent {
  event_type: 'step_event';
  run_id: string;
  step: StepName;
  status: StepStatus;
  timestamp: string;
  data?: Record<string, unknown>;
}

export interface PipelineCompleteEvent {
  event_type: 'pipeline_complete';
  run_id: string;
  timestamp: string;
  report: AnalysisReport;
  completeness: 'complete' | 'partial' | 'minimal';
}

export interface PipelineFailedEvent {
  event_type: 'pipeline_failed';
  run_id: string;
  timestamp: string;
  reason: string;
  failed_step?: string;
}

export interface PipelineTimeoutEvent {
  event_type: 'pipeline_timeout';
  run_id: string;
  timestamp: string;
  reason: string;
}

export interface StreamEndEvent {
  event_type: 'stream_end';
}

// ─── Discriminated union ────────────────────────────────────────────────────

export type PipelineEvent =
  | StepEvent
  | PipelineCompleteEvent
  | PipelineFailedEvent
  | PipelineTimeoutEvent
  | StreamEndEvent;
