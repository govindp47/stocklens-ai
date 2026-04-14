/**
 * API Documentation Page — static React Server Component at /docs.
 *
 * No 'use client' directive — this page is statically generated at build time
 * and requires no client-side JavaScript to render.
 *
 * Documents all five StockLens AI API endpoints.
 */

import type { Metadata } from "next";
import { EndpointBlock } from "@/components/docs/EndpointBlock";

export const metadata: Metadata = {
  title: "API Documentation — StockLens AI",
  description: "REST API reference for the StockLens AI backend.",
};

// ─── Endpoint definitions ─────────────────────────────────────────────────────

const ANALYZE_REQUEST = `{
  "ticker": "AAPL"
}`;

const ANALYZE_RESPONSE = `{
  "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "accepted"
}`;

const ANALYZE_CURL = `curl -X POST https://api.stocklens.example.com/api/v1/analyze \\
  -H "Content-Type: application/json" \\
  -d '{"ticker": "AAPL"}'`;

const STREAM_RESPONSE = `# Server-Sent Events stream
data: {"event_type":"step_event","step":"ticker_validation","status":"completed","step_index":1}

data: {"event_type":"step_event","step":"market_data_collection","status":"completed","step_index":2}

data: {"event_type":"pipeline_complete","run_id":"...","report":{...},"completeness":"complete"}`;

const STREAM_CURL = `curl -N https://api.stocklens.example.com/api/v1/analyze/stream/3fa85f64-5717-4562-b3fc-2c963f66afa6 \\
  -H "Accept: text/event-stream"`;

const RESULTS_RESPONSE = `{
  "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "ticker": "AAPL",
  "generated_at": "2026-03-30T12:00:00Z",
  "completeness": "complete",
  "company": { "ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology" },
  "market_data": { "available": true, "price": 182.63, "change_pct": 1.23 },
  "news": { "available": true, "articles": [...] },
  "sentiment": { "available": true, "dominant": "positive", "distribution": { "positive": 70, "neutral": 20, "negative": 10 } },
  "events": { "available": true, "events": [...] },
  "insights": { "available": true, "sections": {...}, "disclaimer": "..." },
  "data_sources": [...],
  "partial_data_notices": [],
  "error_notices": []
}`;

const RESULTS_CURL = `curl https://api.stocklens.example.com/api/v1/results/3fa85f64-5717-4562-b3fc-2c963f66afa6`;

const NEWS_RESPONSE = `{
  "available": true,
  "articles": [
    {
      "article_id": "abc123",
      "url": "https://example.com/news/apple-earnings",
      "title": "Apple Reports Record Quarterly Earnings",
      "published_at": "2026-03-28T09:00:00Z",
      "source_name": "Reuters",
      "summary": "Apple reported a record quarterly earnings beat...",
      "topics": ["Earnings", "Revenue"],
      "sentiment": "positive",
      "sentiment_score": 0.85,
      "summarization_failed": false
    }
  ]
}`;

const NEWS_CURL = `curl https://api.stocklens.example.com/api/v1/news/AAPL`;

const METRICS_RESPONSE = `{
  "window_hours": 1,
  "bucket_count": 12,
  "buckets": [
    { "ts": "2026-03-30T11:00:00Z", "requests": 42, "completed": 40, "failed": 2 }
  ]
}`;

const METRICS_CURL = `curl https://api.stocklens.example.com/api/v1/metrics`;

const RUNS_RESPONSE = `{
  "total": 2,
  "limit": 50,
  "offset": 0,
  "runs": [
    {
      "run_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "ticker": "AAPL",
      "status": "completed",
      "created_at": "2026-03-30T11:55:00Z",
      "completed_at": "2026-03-30T12:00:00Z",
      "duration_ms": 300000,
      "llm_provider": "ollama",
      "llm_model": "llama3",
      "steps_total": 8,
      "steps_completed": 8,
      "steps_failed": 0
    }
  ]
}`;

const RUNS_CURL = `curl "https://api.stocklens.example.com/api/v1/runs?limit=50&offset=0"`;

// ─── Error code table ─────────────────────────────────────────────────────────

const ERROR_CODES = [
  {
    code: "RATE_LIMIT_EXCEEDED",
    status: 429,
    description: "Too many requests. See Retry-After header.",
  },
  {
    code: "RUN_NOT_FOUND",
    status: 404,
    description: "The specified run_id does not exist or has expired.",
  },
  {
    code: "TICKER_NOT_RESOLVABLE",
    status: 422,
    description: "The ticker could not be resolved to a known company.",
  },
  {
    code: "INVALID_TICKER_FORMAT",
    status: 422,
    description: "The ticker contains invalid characters or is too long.",
  },
  {
    code: "PIPELINE_TIMEOUT",
    status: 504,
    description: "The pipeline exceeded the maximum allowed duration.",
  },
  {
    code: "INTERNAL_ERROR",
    status: 500,
    description: "An unexpected server error occurred.",
  },
];

// ─── Rate limit table ─────────────────────────────────────────────────────────

const RATE_LIMITS = [
  {
    endpoint: "POST /api/v1/analyze",
    limit: "10 requests / 60 seconds per IP",
  },
  {
    endpoint: "GET /api/v1/analyze/stream/:id",
    limit: "No rate limit (read-only)",
  },
  { endpoint: "GET /api/v1/news/:ticker", limit: "No rate limit (read-only)" },
  { endpoint: "GET /api/v1/results/:id", limit: "No rate limit (read-only)" },
  { endpoint: "GET /api/v1/runs", limit: "No rate limit (read-only)" },
  { endpoint: "GET /api/v1/metrics", limit: "No rate limit (read-only)" },
];

// ─── Sidebar nav items ────────────────────────────────────────────────────────

const NAV_LINKS = [
  { id: "endpoint-analyze", label: "POST /api/v1/analyze" },
  { id: "endpoint-stream", label: "GET /analyze/stream/:id" },
  { id: "endpoint-news", label: "GET /news/:ticker" },
  { id: "endpoint-results", label: "GET /results/:id" },
  { id: "endpoint-runs", label: "GET /runs" },
  { id: "endpoint-metrics", label: "GET /metrics" },
  { id: "section-rate-limits", label: "Rate Limits" },
  { id: "section-error-codes", label: "Error Codes" },
];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DocsPage() {
  return (
    <div id="main-content" className="max-w-6xl mx-auto px-4 py-10">
      {/* Page header */}
      <div className="mb-8">
        <h1 className="mt-4 text-2xl font-bold text-neutral-900">
          StockLens AI — API Reference
        </h1>
        <p className="mt-2 text-sm text-neutral-600">
          All endpoints are prefixed with{" "}
          <code className="px-1 py-0.5 bg-neutral-100 rounded text-xs font-mono">
            /api/v1
          </code>
          . The base URL in production is{" "}
          <code className="px-1 py-0.5 bg-neutral-100 rounded text-xs font-mono">
            https://api.stocklens.example.com
          </code>
          .
        </p>
      </div>

      {/* ── Two-column layout ──────────────────────────────────────────────── */}
      {/* On mobile: stacked (flex-col); on lg+: side-by-side (flex-row) */}
      <div className="flex flex-col lg:flex-row gap-8">
        {/* ── Sticky sidebar ─────────────────────────────────────────────── */}
        <aside className="lg:w-52 lg:shrink-0">
          <nav aria-label="Endpoint navigation" className="lg:sticky lg:top-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-neutral-400">
              On this page
            </p>
            <ul className="space-y-2">
              {NAV_LINKS.map(({ id, label }) => (
                <li key={id}>
                  <a
                    href={`#${id}`}
                    className="block text-sm text-neutral-600 hover:text-brand-500 transition-colors"
                  >
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </aside>

        {/* ── Main content ───────────────────────────────────────────────── */}
        <main className="flex-1 min-w-0">
          {/* ── Endpoints ──────────────────────────────────────────────────────── */}
          <h2 className="text-lg font-semibold text-neutral-800 mb-4">
            Endpoints
          </h2>

          <EndpointBlock
            id="endpoint-analyze"
            method="POST"
            path="/api/v1/analyze"
            description="Trigger a new stock analysis pipeline for the given ticker. Returns a run_id immediately; poll the SSE stream for results."
            requestBody={ANALYZE_REQUEST}
            responseSchema={ANALYZE_RESPONSE}
            curlExample={ANALYZE_CURL}
            notes={[
              "Rate limited: 10 requests per 60-second window per IP address.",
              "Idempotent within a short window: a second request for the same ticker from the same IP returns the existing run_id.",
              "Pass X-OpenAI-Key header to use GPT-4o instead of the local Ollama model.",
            ]}
          />

          <EndpointBlock
            id="endpoint-stream"
            method="GET"
            path="/api/v1/analyze/stream/{run_id}"
            description="Subscribe to the SSE event stream for a pipeline run. Events are replayed from the beginning on reconnect — safe for use with SSE reconnect logic."
            responseSchema={STREAM_RESPONSE}
            curlExample={STREAM_CURL}
            notes={[
              "Content-Type: text/event-stream",
              "Events: step_event, pipeline_complete, pipeline_failed, pipeline_timeout, stream_end",
              "The stream closes automatically after pipeline_complete or pipeline_failed.",
              "Returns 404 if the run_id does not exist.",
            ]}
          />

          <EndpointBlock
            id="endpoint-news"
            method="GET"
            path="/api/v1/news/{ticker}"
            description="Retrieve the most recently fetched and summarised news articles for a ticker. Returns cached results from the most recent completed run."
            responseSchema={NEWS_RESPONSE}
            curlExample={NEWS_CURL}
            notes={[
              "Returns 404 if no completed run exists for this ticker.",
              "Articles are sorted by published_at descending.",
            ]}
          />

          <EndpointBlock
            id="endpoint-results"
            method="GET"
            path="/api/v1/results/{run_id}"
            description="Retrieve the completed analysis report for a given run. Returns 404 if the run has not completed, does not exist, or has been cleaned up (TTL: 24 hours)."
            responseSchema={RESULTS_RESPONSE}
            curlExample={RESULTS_CURL}
            notes={[
              "Reports are retained for 24 hours after creation.",
              "The completeness field is one of: complete, partial, minimal.",
            ]}
          />

          <EndpointBlock
            id="endpoint-runs"
            method="GET"
            path="/api/v1/runs"
            description="List all successfully completed analysis runs, ordered by completion time descending. Report data is not included; use GET /api/v1/results/{run_id} to fetch the full report."
            responseSchema={RUNS_RESPONSE}
            curlExample={RUNS_CURL}
            notes={[
              "Supports pagination via limit (1–200, default 50) and offset query parameters.",
              "Only completed runs are returned; in-progress or failed runs are excluded.",
            ]}
          />

          <EndpointBlock
            id="endpoint-metrics"
            method="GET"
            path="/api/v1/metrics"
            description="Retrieve system throughput metrics for the current sliding window. Used for operational monitoring."
            responseSchema={METRICS_RESPONSE}
            curlExample={METRICS_CURL}
          />

          {/* ── Rate limits ────────────────────────────────────────────────────── */}
          <section id="section-rate-limits" className="mb-8">
            <h2 className="text-lg font-semibold text-neutral-800 mb-3">
              Rate Limits
            </h2>
            <div className="overflow-x-auto rounded-lg border border-neutral-200">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-neutral-50 text-left">
                    <th className="px-4 py-2 text-xs font-semibold text-neutral-600 border-b border-neutral-200">
                      Endpoint
                    </th>
                    <th className="px-4 py-2 text-xs font-semibold text-neutral-600 border-b border-neutral-200">
                      Limit
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {RATE_LIMITS.map(({ endpoint, limit }) => (
                    <tr
                      key={endpoint}
                      className="border-b border-neutral-100 last:border-0"
                    >
                      <td className="px-4 py-2 font-mono text-xs text-neutral-700">
                        {endpoint}
                      </td>
                      <td className="px-4 py-2 text-xs text-neutral-600">
                        {limit}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-xs text-neutral-500">
              Rate-limited responses include a{" "}
              <code className="px-1 py-0.5 bg-neutral-100 rounded font-mono">
                Retry-After
              </code>{" "}
              header with the number of seconds until the window resets.
            </p>
          </section>

          {/* ── Error codes ────────────────────────────────────────────────────── */}
          <section id="section-error-codes" className="mb-8">
            <h2 className="text-lg font-semibold text-neutral-800 mb-3">
              Error Codes
            </h2>
            <p className="text-sm text-neutral-600 mb-3">
              All error responses use the following JSON shape:
            </p>
            <div className="mb-4 rounded-md bg-neutral-900 overflow-x-auto">
              <pre className="px-4 py-3 text-xs text-neutral-100 font-mono">
                <code>{`{
  "error_code": "RATE_LIMIT_EXCEEDED",
  "message": "Too many requests",
  "retry_after": 60
}`}</code>
              </pre>
            </div>

            <div className="overflow-x-auto rounded-lg border border-neutral-200">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-neutral-50 text-left">
                    <th className="px-4 py-2 text-xs font-semibold text-neutral-600 border-b border-neutral-200">
                      Error Code
                    </th>
                    <th className="px-4 py-2 text-xs font-semibold text-neutral-600 border-b border-neutral-200">
                      HTTP Status
                    </th>
                    <th className="px-4 py-2 text-xs font-semibold text-neutral-600 border-b border-neutral-200">
                      Description
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {ERROR_CODES.map(({ code, status, description }) => (
                    <tr
                      key={code}
                      className="border-b border-neutral-100 last:border-0"
                    >
                      <td className="px-4 py-2 font-mono text-xs text-neutral-700">
                        {code}
                      </td>
                      <td className="px-4 py-2 text-xs text-neutral-600">
                        {status}
                      </td>
                      <td className="px-4 py-2 text-xs text-neutral-600">
                        {description}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* ── Disclaimer ─────────────────────────────────────────────────────── */}
          <footer className="mt-10 pt-6 border-t border-neutral-200">
            <p className="text-xs text-neutral-400">
              StockLens AI is for informational purposes only and does not
              constitute financial, investment, or trading advice.
            </p>
          </footer>
        </main>
        {/* end main content column */}
      </div>
      {/* end two-column flex */}
    </div>
  );
}
