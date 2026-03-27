/**
 * Typed fetch wrappers for the StockLens AI backend API.
 *
 * All functions throw typed errors on non-2xx responses so callers
 * can handle rate limiting and not-found cases explicitly.
 */

import type { AnalyzeResponse, AnalysisReport, SystemMetrics } from '../types/report';

// ─── Base URL ─────────────────────────────────────────────────────────────────

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? '';

// ─── Custom error classes ─────────────────────────────────────────────────────

export class RateLimitError extends Error {
  readonly retryAfter: number;

  constructor(retryAfter: number) {
    super(`Rate limit exceeded. Retry after ${retryAfter} seconds.`);
    this.name = 'RateLimitError';
    this.retryAfter = retryAfter;
  }
}

export class NotFoundError extends Error {
  constructor(resource: string) {
    super(`Resource not found: ${resource}`);
    this.name = 'NotFoundError';
  }
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

// ─── Type guard ───────────────────────────────────────────────────────────────

export function isRateLimitError(err: unknown): err is RateLimitError {
  return err instanceof RateLimitError;
}

// ─── Internal helper ──────────────────────────────────────────────────────────

async function handleResponse<T>(response: Response, resource = ''): Promise<T> {
  if (response.ok) {
    return response.json() as Promise<T>;
  }

  if (response.status === 429) {
    const retryAfter = parseInt(response.headers.get('Retry-After') ?? '60', 10);
    throw new RateLimitError(retryAfter);
  }

  if (response.status === 404) {
    throw new NotFoundError(resource);
  }

  let message = `API error ${response.status}`;
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') {
      message = body.detail;
    } else if (typeof body?.detail?.message === 'string') {
      message = body.detail.message;
    }
  } catch {
    // ignore JSON parse errors; use default message
  }

  throw new ApiError(response.status, message);
}

// ─── API functions ────────────────────────────────────────────────────────────

/**
 * POST /api/v1/analyze
 *
 * Triggers a new pipeline run (or returns an existing idempotent run_id).
 * Pass openAiKey only when the user has provided one in the settings panel.
 *
 * @throws {RateLimitError} when the backend returns 429
 * @throws {ApiError} on any other non-2xx response
 */
export async function triggerAnalysis(
  ticker: string,
  openAiKey?: string,
): Promise<AnalyzeResponse> {
  const body: Record<string, string> = { ticker };
  if (openAiKey) {
    body.openai_api_key = openAiKey;
  }

  const response = await fetch(`${BASE_URL}/api/v1/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  return handleResponse<AnalyzeResponse>(response, 'analyze');
}

/**
 * GET /api/v1/results/{runId}
 *
 * Retrieves the completed analysis report for a given run.
 *
 * @throws {NotFoundError} when run_id does not exist or is not yet complete
 * @throws {ApiError} on any other non-2xx response
 */
export async function getPastResult(runId: string): Promise<AnalysisReport> {
  const response = await fetch(`${BASE_URL}/api/v1/results/${runId}`);
  const data = await handleResponse<{ report: AnalysisReport }>(response, runId);
  return data.report;
}

/**
 * GET /api/v1/metrics
 *
 * Returns the last 24 h of hourly pipeline metrics.
 *
 * @throws {ApiError} on non-2xx response
 */
export async function getMetrics(): Promise<SystemMetrics> {
  const response = await fetch(`${BASE_URL}/api/v1/metrics`);
  return handleResponse<SystemMetrics>(response, 'metrics');
}
