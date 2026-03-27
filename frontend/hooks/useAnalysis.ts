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
 */

'use client';

import { useCallback } from 'react';
import { useAnalysisStore, useSettingsStore } from '../store';
import { useSSEStream } from './useSSEStream';
import * as api from '../lib/api';
import { parseSSEEvent } from '../lib/sse';
import type {
  PipelineCompleteEvent,
  PipelineFailedEvent,
} from '../types/pipeline';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? '';

export function useAnalysis() {
  const {
    startAnalysis,
    appendStepEvent,
    setPipelineComplete,
    setPipelineFailed,
    reset,
  } = useAnalysisStore();

  const { openAiKey, markKeyInvalid } = useSettingsStore();
  const { openSSE, closeSSE } = useSSEStream();

  const analyze = useCallback(
    async (ticker: string) => {
      reset();
      startAnalysis(ticker);

      // ── Step 1: POST /api/v1/analyze ──────────────────────────────────────
      let runId: string;
      try {
        const response = await api.triggerAnalysis(ticker, openAiKey || undefined);
        runId = response.run_id;
      } catch (error) {
        if (api.isRateLimitError(error)) {
          setPipelineFailed({
            reason: 'Rate limit exceeded. Please wait a moment before trying again.',
          });
        } else {
          setPipelineFailed({
            reason: 'Failed to start analysis. Please try again.',
          });
        }
        return;
      }

      // ── Step 2: Open SSE stream ───────────────────────────────────────────
      openSSE(`${BASE_URL}/api/v1/analyze/stream/${runId}`, {
        onEvent: (rawData: string) => {
          const event = parseSSEEvent(rawData);
          if (!event) return;

          switch (event.event_type) {
            case 'step_event':
              appendStepEvent(event);
              break;

            case 'pipeline_complete':
              setPipelineComplete(event as PipelineCompleteEvent);
              closeSSE();
              break;

            case 'pipeline_failed': {
              const failed = event as PipelineFailedEvent;
              // Invalidate the OpenAI key if the backend signals auth failure.
              if (failed.failed_step === 'openai_auth') {
                markKeyInvalid();
              }
              setPipelineFailed(failed);
              closeSSE();
              break;
            }

            case 'pipeline_timeout':
              setPipelineFailed({
                reason: 'Analysis timed out. Please try again.',
              });
              closeSSE();
              break;

            case 'stream_end':
              // Backend signals clean end of buffered events stream.
              closeSSE();
              break;
          }
        },

        onError: () => {
          setPipelineFailed({
            reason: 'Connection to analysis stream was lost.',
          });
        },
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [openAiKey],
  );

  return { analyze };
}
