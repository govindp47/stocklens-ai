/**
 * MSW handlers — mock responses for all five StockLens AI API endpoints.
 *
 * The analyze handler returns a fixed run_id.
 * The stream handler returns a sequence of SSE events ending with pipeline_complete.
 */

import { http, HttpResponse } from "msw";

// ─── Fixed mock run_id ────────────────────────────────────────────────────────

export const MOCK_RUN_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

// ─── Mock report data ─────────────────────────────────────────────────────────

export const MOCK_REPORT = {
  run_id: MOCK_RUN_ID,
  ticker: "AAPL",
  generated_at: "2026-03-30T12:00:00Z",
  schema_version: "1.0",
  completeness: "complete",
  company: {
    ticker: "AAPL",
    name: "Apple Inc.",
    exchange: "NASDAQ",
    sector: "Technology",
    industry: "Consumer Electronics",
    currency: "USD",
    country: "US",
  },
  market_data: {
    available: true,
    price: 182.63,
    change_pct: 1.23,
    change_abs: 2.21,
    volume: 55120000,
    market_cap: 2710000000000,
    pe_ratio: 28.5,
    week_52_high: 199.62,
    week_52_low: 143.9,
    currency: "USD",
    data_delayed_minutes: 0,
    as_of: "2026-03-30T16:00:00Z",
  },
  price_history: {
    available: true,
    datapoints: [
      {
        date: "2026-03-01",
        open: 175.0,
        high: 178.0,
        low: 174.5,
        close: 177.2,
        volume: 50000000,
      },
      {
        date: "2026-03-15",
        open: 180.0,
        high: 183.0,
        low: 179.0,
        close: 182.63,
        volume: 55120000,
      },
    ],
    trend_direction: "up",
    volatility_flag: false,
  },
  news: {
    available: true,
    articles: [
      {
        article_id: "art1",
        url: "https://example.com/apple-earnings",
        title: "Apple Reports Record Quarterly Earnings",
        published_at: "2026-03-28T09:00:00Z",
        source_name: "Reuters",
        content_snippet: "Apple beat expectations...",
        summary:
          "Apple reported a record quarterly earnings beat driven by iPhone sales.",
        topics: ["Earnings", "Revenue"],
        sentiment: "positive",
        sentiment_score: 0.85,
        summarization_failed: false,
      },
      {
        article_id: "art2",
        url: "https://example.com/apple-ai",
        title: "Apple Expands AI Features in iOS Update",
        published_at: "2026-03-27T14:30:00Z",
        source_name: "Bloomberg",
        content_snippet: "Apple announced new AI features...",
        summary: "Apple announced an expansion of on-device AI capabilities.",
        topics: ["AI", "Product"],
        sentiment: "positive",
        sentiment_score: 0.78,
        summarization_failed: false,
      },
    ],
  },
  sentiment: {
    available: true,
    distribution: { positive: 70, neutral: 20, negative: 10 },
    dominant: "positive",
    article_count: 2,
    limited_data_caveat: false,
    emerging_concern_flag: false,
  },
  events: {
    available: true,
    events: [
      {
        event_type: "Earnings Announcement",
        description:
          "Apple reported Q2 2026 earnings that exceeded analyst expectations.",
        detected_date: "2026-03-28",
        source_article_indices: [0],
      },
    ],
  },
  insights: {
    available: true,
    sections: {
      company_overview:
        "Apple Inc. is the world's largest technology company by market capitalisation.",
      recent_developments:
        "Apple recently reported record quarterly earnings and announced new AI features.",
      sentiment_overview:
        "Overall sentiment is predominantly positive, driven by strong earnings and AI momentum.",
      potential_drivers:
        "Key growth drivers include iPhone upgrade cycle, services revenue growth, and AI adoption.",
      potential_risks:
        "Potential risks include macroeconomic headwinds and increased competition in the smartphone market.",
      ai_summary:
        "Apple presents a strong investment thesis supported by solid fundamentals and AI-driven growth.",
    },
    disclaimer:
      "This is AI-generated analysis for informational purposes only.",
  },
  data_sources: [
    {
      name: "yfinance (Market Data)",
      status: "ok",
      detail: "Fetched successfully",
    },
    { name: "RSS News Feed", status: "ok", detail: "12 articles retrieved" },
    { name: "Ollama (LLM)", status: "ok", detail: "mistral:7b-instruct" },
  ],
  partial_data_notices: [],
  error_notices: [],
  content_hash: null,
};

// ─── SSE event sequence ───────────────────────────────────────────────────────

function buildSSEStream(): string {
  const steps = [
    {
      event_type: "step_event",
      step: "ticker_validation",
      status: "completed",
      step_index: 1,
      duration_ms: 150,
    },
    {
      event_type: "step_event",
      step: "market_data_collection",
      status: "completed",
      step_index: 2,
      duration_ms: 320,
    },
    {
      event_type: "step_event",
      step: "news_retrieval",
      status: "completed",
      step_index: 3,
      duration_ms: 800,
    },
    {
      event_type: "step_event",
      step: "news_deduplication",
      status: "completed",
      step_index: 4,
      duration_ms: 50,
    },
    {
      event_type: "step_event",
      step: "article_summarization",
      status: "completed",
      step_index: 5,
      duration_ms: 2100,
    },
    {
      event_type: "step_event",
      step: "sentiment_classification",
      status: "completed",
      step_index: 6,
      duration_ms: 900,
    },
    {
      event_type: "step_event",
      step: "event_extraction",
      status: "completed",
      step_index: 7,
      duration_ms: 600,
    },
    {
      event_type: "step_event",
      step: "insight_generation",
      status: "completed",
      step_index: 8,
      duration_ms: 3200,
    },
    {
      event_type: "step_event",
      step: "report_assembly",
      status: "completed",
      step_index: 9,
      duration_ms: 120,
    },
  ];

  const pipelineComplete = {
    event_type: "pipeline_complete",
    run_id: MOCK_RUN_ID,
    report: MOCK_REPORT,
    completeness: "complete",
  };

  const frames = steps.map((s) => `data: ${JSON.stringify(s)}\n\n`).join("");
  const completeFrame = `data: ${JSON.stringify(pipelineComplete)}\n\n`;
  return frames + completeFrame;
}

// ─── Handlers ─────────────────────────────────────────────────────────────────

export const handlers = [
  // POST /api/v1/analyze
  http.post("/api/v1/analyze", () => {
    return HttpResponse.json(
      { run_id: MOCK_RUN_ID, status: "accepted" },
      { status: 202 },
    );
  }),

  // GET /api/v1/analyze/stream/:run_id
  http.get("/api/v1/analyze/stream/:run_id", () => {
    const body = buildSSEStream();
    return new HttpResponse(body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
      },
    });
  }),

  // GET /api/v1/results/:run_id
  http.get("/api/v1/results/:run_id", ({ params }) => {
    const { run_id } = params;
    if (run_id !== MOCK_RUN_ID) {
      return HttpResponse.json(
        { error_code: "RUN_NOT_FOUND", message: "Run not found" },
        { status: 404 },
      );
    }
    return HttpResponse.json(MOCK_REPORT);
  }),

  // GET /api/v1/news/:ticker
  http.get("/api/v1/news/:ticker", () => {
    return HttpResponse.json(MOCK_REPORT.news);
  }),

  // GET /api/v1/metrics
  http.get("/api/v1/metrics", () => {
    return HttpResponse.json({
      window_hours: 1,
      bucket_count: 1,
      buckets: [
        { ts: "2026-03-30T12:00:00Z", requests: 5, completed: 5, failed: 0 },
      ],
    });
  }),
];
