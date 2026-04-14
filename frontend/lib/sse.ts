/**
 * SSE frame parser utility.
 *
 * Parses a raw SSE frame string (the text after splitting on \n\n) and
 * returns the parsed PipelineEvent or null if the frame has no valid data line
 * or the JSON cannot be parsed.
 *
 * Normalizes the backend event shape to the frontend's expected types:
 * - Backend uses `type` as the discriminator; frontend expects `event_type`.
 * - Backend step status values ("running", "complete") are mapped to frontend
 *   values ("started", "completed").
 * - Backend `step_name` field is mapped to `step`.
 * - Backend `pipeline_started` events are dropped (no frontend handler).
 *
 * This utility is intentionally side-effect-free so it can be unit-tested
 * without any browser or React dependencies.
 */

import type { PipelineEvent } from "../types/pipeline";

/** Backend raw event shapes (as actually emitted by the Python backend). */
interface BackendStepUpdateEvent {
  type: "step_update";
  run_id?: string;
  step_name: string;
  step_index: number;
  status: "running" | "complete" | "failed" | "skipped";
  duration_ms?: number;
  reason?: string;
  output_summary?: string;
}

interface BackendPipelineStartedEvent {
  type: "pipeline_started";
  run_id: string;
  ticker: string;
}

interface BackendPipelineCompleteEvent {
  type: "pipeline_complete";
  run_id: string;
  steps_completed: number;
}

interface BackendPipelineFailedEvent {
  type: "pipeline_failed";
  run_id: string;
  reason: string;
  failed_step?: string;
  failed_step_is_critical?: boolean;
  steps_completed?: number;
  steps_failed?: number;
}

interface BackendPipelineTimeoutEvent {
  type: "pipeline_timeout";
  run_id: string;
}

interface BackendStreamEndEvent {
  type: "stream_end";
}

type BackendEvent =
  | BackendStepUpdateEvent
  | BackendPipelineStartedEvent
  | BackendPipelineCompleteEvent
  | BackendPipelineFailedEvent
  | BackendPipelineTimeoutEvent
  | BackendStreamEndEvent;

/** Map backend PascalCase step names to frontend snake_case StepName values. */
const STEP_NAME_MAP: Record<string, string> = {
  TickerValidator: "ticker_validation",
  MarketDataCollector: "market_data_collection",
  NewsRetriever: "news_retrieval",
  NewsDeduplicator: "news_deduplication",
  ArticleSummarizer: "article_summarization",
  SentimentClassifier: "sentiment_classification",
  EventExtractor: "event_extraction",
  InsightGenerator: "insight_generation",
  ReportAssembler: "report_assembly",
};

function normalizeStepName(name: string): string {
  return STEP_NAME_MAP[name] ?? name;
}

/** Map backend step status values to frontend StepStatus values. */
function normalizeStepStatus(
  status: string,
): "started" | "completed" | "failed" | "skipped" {
  switch (status) {
    case "running":
      return "started";
    case "complete":
      return "completed";
    case "failed":
      return "failed";
    case "skipped":
      return "skipped";
    default:
      return "started";
  }
}

/** Normalize a raw backend event object into the frontend's PipelineEvent shape. */
function normalizeEvent(raw: BackendEvent): PipelineEvent | null {
  switch (raw.type) {
    case "step_update":
      return {
        event_type: "step_event",
        run_id: raw.run_id ?? "",
        step: normalizeStepName(raw.step_name),
        status: normalizeStepStatus(raw.status),
        timestamp: new Date().toISOString(),
        data:
          raw.duration_ms !== undefined
            ? { duration_ms: raw.duration_ms }
            : undefined,
      } as PipelineEvent;

    case "pipeline_complete":
      return {
        event_type: "pipeline_complete",
        run_id: raw.run_id,
        timestamp: new Date().toISOString(),
        // report is intentionally absent here; useAnalysis fetches it separately
        // via GET /api/v1/results/{run_id} after receiving this event.
        report: null as never,
        completeness: "complete",
      } as PipelineEvent;

    case "pipeline_failed":
      return {
        event_type: "pipeline_failed",
        run_id: raw.run_id,
        timestamp: new Date().toISOString(),
        reason: raw.reason,
        failed_step: raw.failed_step,
      } as PipelineEvent;

    case "pipeline_timeout":
      return {
        event_type: "pipeline_timeout",
        run_id: raw.run_id,
        timestamp: new Date().toISOString(),
        reason: "Pipeline timed out",
      } as PipelineEvent;

    case "stream_end":
      return { event_type: "stream_end" };

    case "pipeline_started":
      // No frontend handler for this event; safely ignore it.
      return null;

    default:
      return null;
  }
}

/**
 * Parse a raw JSON string (already stripped of the "data: " prefix by
 * useSSEStream) into a typed PipelineEvent.
 *
 * @param jsonString  The raw JSON payload from an SSE data line.
 * @returns The parsed and normalized event, or null on any parse failure.
 */
export function parseSSEEvent(jsonString: string): PipelineEvent | null {
  let raw: BackendEvent;
  try {
    raw = JSON.parse(jsonString) as BackendEvent;
  } catch {
    return null;
  }

  return normalizeEvent(raw);
}
