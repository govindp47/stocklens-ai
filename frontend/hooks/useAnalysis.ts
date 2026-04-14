/**
 * useAnalysis — orchestrates the full analysis lifecycle:
 *
 *   1. POST /api/v1/analyze  → receives run_id
 *   2. Open SSE stream       → dispatches step events to the store
 *   3. On pipeline_complete  → populates all report panel data
 *   4. On pipeline_failed    → sets error message in the store
 *
 * Error handling:
 * - RateLimitError from triggerAnalysis sets a user-friendly failed state.
 * - Other fetch errors set a generic failed state.
 * - OpenAI auth failures (failed_step === 'openai_auth') also call markKeyInvalid().
 * - A client-side watchdog timer (120s of silence) auto-fails the pipeline
 *   if the SSE stream silently drops without sending a terminal event.
 */

"use client";

import { useCallback } from "react";
import { useAnalysisStore, useSettingsStore } from "../store";
import { useSSEStream } from "./useSSEStream";
import * as api from "../lib/api";
import { parseSSEEvent } from "../lib/sse";
import { useHistoryStore } from "../store/historySlice";
import type {
  PipelineCompleteEvent,
  PipelineFailedEvent,
} from "../types/pipeline";
import type { AnalysisReport } from "../types/report";

/** Milliseconds of SSE silence before the client-side watchdog fires. */
const WATCHDOG_TIMEOUT_MS = 600_000;

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost";

export function useAnalysis() {
  const {
    startAnalysis,
    setRunId,
    appendStepEvent,
    setPipelineComplete,
    setPipelineFailed,
    reset,
  } = useAnalysisStore();

  const { openAiKey, markKeyInvalid, selectedProvider } = useSettingsStore();
  const { openSSE, closeSSE } = useSSEStream();
  const { addEntry } = useHistoryStore();

  const analyze = useCallback(
    async (ticker: string) => {
      reset();
      startAnalysis(ticker);

      // ── Step 1: POST /api/v1/analyze ──────────────────────────────────────
      let runId: string;
      try {
        const response = await api.triggerAnalysis(ticker, {
          openAiKey:
            selectedProvider === "openai" ? openAiKey || undefined : undefined,
          provider: selectedProvider,
        });
        runId = response.run_id;
        setRunId(runId);
      } catch (error) {
        if (api.isRateLimitError(error)) {
          setPipelineFailed({
            reason:
              "Rate limit exceeded. Please wait a moment before trying again.",
          });
        } else {
          setPipelineFailed({
            reason: "Failed to start analysis. Please try again.",
          });
        }
        return;
      }

      // ── Step 2: Open SSE stream with client-side watchdog ─────────────────
      let watchdogTimer: ReturnType<typeof setTimeout> | null = null;

      const clearWatchdog = () => {
        if (watchdogTimer !== null) {
          clearTimeout(watchdogTimer);
          watchdogTimer = null;
        }
      };

      const resetWatchdog = () => {
        clearWatchdog();
        watchdogTimer = setTimeout(() => {
          setPipelineFailed({
            reason:
              "Analysis timed out waiting for a response. Please try again.",
          });
          closeSSE();
        }, WATCHDOG_TIMEOUT_MS);
      };

      // Start the watchdog immediately — any incoming SSE event will reset it.
      resetWatchdog();

      // SSE must bypass Next.js rewrites (Next.js buffers responses, breaking streaming).
      // Using window.location.origin routes directly through Nginx which has
      // proxy_buffering off for this path.
      const sseUrl = `${API_BASE}/api/v1/analyze/stream/${runId}`;

      openSSE(sseUrl, {
        onEvent: (rawData: string) => {
          // Reset watchdog on every received event (proves stream is alive).
          resetWatchdog();

          const event = parseSSEEvent(rawData);
          if (!event) return;

          switch (event.event_type) {
            case "step_event":
              appendStepEvent(event);
              break;

            case "pipeline_complete":
              clearWatchdog();
              closeSSE();
              // The pipeline_complete SSE event doesn't include the full report.
              // Fetch it from the results endpoint now that the run is complete.
              api
                .getPastResult(runId)
                .then((report: AnalysisReport) => {
                  setPipelineComplete({
                    ...(event as PipelineCompleteEvent),
                    report,
                  });
                  addEntry({
                    runId,
                    ticker: report.ticker,
                    companyName: report.company?.name ?? undefined,
                    timestamp: new Date().toISOString(),
                    completeness: report.completeness,
                  });
                })
                .catch(() => {
                  setPipelineFailed({
                    reason:
                      "Analysis completed but report could not be retrieved.",
                  });
                });
              break;

            case "pipeline_failed": {
              clearWatchdog();
              const failed = event as PipelineFailedEvent;
              // Invalidate the OpenAI key if the backend signals auth failure.
              if (failed.failed_step === "openai_auth") {
                markKeyInvalid();
              }
              setPipelineFailed(failed);
              closeSSE();
              break;
            }

            case "pipeline_timeout":
              clearWatchdog();
              setPipelineFailed({
                reason: "Analysis timed out. Please try again.",
              });
              closeSSE();
              break;

            case "stream_end":
              // Backend signals clean end of buffered events stream.
              clearWatchdog();
              closeSSE();
              break;
          }
        },

        onError: () => {
          clearWatchdog();
          setPipelineFailed({
            reason: "Connection to analysis stream was lost.",
          });
        },
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [openAiKey, selectedProvider],
  );

  return { analyze };
}
