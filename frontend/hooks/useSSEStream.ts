/**
 * useSSEStream — SSE connection management using the Fetch API's ReadableStream.
 *
 * Design decisions:
 * - Uses fetch() + ReadableStream instead of EventSource so we can send custom
 *   headers (e.g. Authorization) on every request.
 * - An AbortController gates the entire fetch lifecycle; calling closeSSE() or
 *   component unmount both abort the controller, which cancels the in-flight
 *   fetch and terminates the reader loop cleanly.
 * - Incomplete SSE frames (chunks that don't end with \n\n) are held in a
 *   string buffer and merged with the next chunk before splitting.
 */

'use client';

import { useCallback, useEffect, useRef } from 'react';

export interface SSEHandlers {
  /** Called with the raw data payload (string after "data: ") for each frame. */
  onEvent: (rawData: string) => void;
  /** Called on network error or non-2xx response. Not called for AbortError. */
  onError?: () => void;
}

export function useSSEStream() {
  const readerRef = useRef<ReadableStreamDefaultReader<string> | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  /**
   * Opens an SSE connection to `url`.
   * Any previously open connection is aborted before opening the new one.
   */
  const openSSE = useCallback((url: string, handlers: SSEHandlers) => {
    // Abort any existing connection first.
    abortControllerRef.current?.abort();

    const controller = new AbortController();
    abortControllerRef.current = controller;

    (async () => {
      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: { Accept: 'text/event-stream' },
        });

        if (!response.ok || !response.body) {
          handlers.onError?.();
          return;
        }

        const reader = response.body
          .pipeThrough(new TextDecoderStream())
          .getReader();
        readerRef.current = reader;

        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += value;

          // SSE frames are delimited by \n\n.
          // The last element after split may be a partial frame — keep it in buffer.
          const frames = buffer.split('\n\n');
          buffer = frames.pop() ?? '';

          for (const frame of frames) {
            if (!frame.trim()) continue;

            // Find the data line within the frame.
            const dataLine = frame.split('\n').find((l) => l.startsWith('data: '));
            if (dataLine) {
              handlers.onEvent(dataLine.slice(6)); // strip "data: "
            }
          }
        }
      } catch (error) {
        // AbortError is expected on closeSSE() / unmount — not a real error.
        if ((error as Error).name !== 'AbortError') {
          handlers.onError?.();
        }
      }
    })();
  }, []);

  /**
   * Closes the current SSE connection by aborting the fetch and cancelling
   * the stream reader.
   */
  const closeSSE = useCallback(() => {
    abortControllerRef.current?.abort();
    readerRef.current?.cancel().catch(() => {
      // ignore cancel errors — connection is already gone
    });
    readerRef.current = null;
  }, []);

  // Abort the SSE connection when the component using this hook unmounts.
  useEffect(() => () => closeSSE(), [closeSSE]);

  return { openSSE, closeSSE };
}
