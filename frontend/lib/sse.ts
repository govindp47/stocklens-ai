/**
 * SSE frame parser utility.
 *
 * Parses a raw SSE frame string (the text after splitting on \n\n) and
 * returns the parsed PipelineEvent or null if the frame has no valid data line
 * or the JSON cannot be parsed.
 *
 * This utility is intentionally side-effect-free so it can be unit-tested
 * without any browser or React dependencies.
 */

import type { PipelineEvent } from '../types/pipeline';

/**
 * Parse a single SSE frame into a typed PipelineEvent.
 *
 * An SSE frame may contain multiple lines. We look for the first line starting
 * with "data: " and attempt to JSON-parse the remainder.
 *
 * @param rawFrame  A single SSE frame (content between two \n\n separators).
 * @returns The parsed event, or null on any parse failure.
 */
export function parseSSEEvent(rawFrame: string): PipelineEvent | null {
  const lines = rawFrame.split('\n');
  const dataLine = lines.find((l) => l.startsWith('data: '));

  if (!dataLine) return null;

  const jsonString = dataLine.slice(6); // strip leading "data: "

  try {
    return JSON.parse(jsonString) as PipelineEvent;
  } catch {
    return null;
  }
}
