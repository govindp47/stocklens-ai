/**
 * TypeScript types mirroring the backend's Pydantic domain models.
 * These are used to type the AnalysisReport delivered via the pipeline_complete SSE event
 * and the GET /api/v1/results/{run_id} response.
 */

// ─── Company ────────────────────────────────────────────────────────────────

export interface CompanyInfo {
  ticker: string;
  name: string | null;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  currency: string | null;
  country: string | null;
}

// ─── Market data ────────────────────────────────────────────────────────────

export interface MarketData {
  available: boolean;
  price: number | null;
  change_pct: number | null;
  change_abs: number | null;
  volume: number | null;
  market_cap: number | null;
  pe_ratio: number | null;
  week_52_high: number | null;
  week_52_low: number | null;
  currency: string;
  data_delayed_minutes: number;
  as_of: string | null; // ISO 8601 datetime string
}

// ─── Price history ──────────────────────────────────────────────────────────

export interface PricePoint {
  date: string; // YYYY-MM-DD
  open: number | null;
  high: number | null;
  low: number | null;
  close: number | null;
  volume: number | null;
}

export interface PriceHistory {
  available: boolean;
  datapoints: PricePoint[];
  trend_direction: string | null; // "up" | "down" | "flat"
  volatility_flag: boolean;
}

// ─── News ───────────────────────────────────────────────────────────────────

export interface ArticleSummary {
  article_id: string;
  url: string;
  title: string;
  published_at: string; // ISO 8601 datetime string
  source_name: string;
  content_snippet: string;
  summary: string;
  topics: string[];
  sentiment: string;
  sentiment_score: number;
  summarization_failed: boolean;
}

export interface NewsCollection {
  available: boolean;
  articles: ArticleSummary[];
}

// ─── Sentiment ──────────────────────────────────────────────────────────────

export interface SentimentDistribution {
  positive: number;
  neutral: number;
  negative: number;
}

export interface SentimentResult {
  available: boolean;
  distribution: SentimentDistribution | null;
  dominant: string | null; // "positive" | "neutral" | "negative"
  article_count: number;
  limited_data_caveat: boolean;
  emerging_concern_flag: boolean;
}

// ─── Events ─────────────────────────────────────────────────────────────────

export interface ExtractedEvent {
  event_type: string;
  description: string;
  detected_date: string; // YYYY-MM-DD
  source_article_indices: number[];
}

export interface EventsResult {
  available: boolean;
  events: ExtractedEvent[];
}

// ─── Insights ───────────────────────────────────────────────────────────────

export interface InsightSections {
  company_overview: string;
  recent_developments: string;
  sentiment_overview: string;
  potential_drivers: string;
  potential_risks: string;
  ai_summary: string;
}

export interface InsightsResult {
  available: boolean;
  sections: InsightSections | null;
  disclaimer: string;
}

// ─── Data sources ────────────────────────────────────────────────────────────

export interface DataSource {
  name: string;
  status: string; // "ok" | "partial" | "unavailable"
  detail: string;
}

// ─── Top-level report ────────────────────────────────────────────────────────

export interface AnalysisReport {
  run_id: string;
  ticker: string;
  generated_at: string; // ISO 8601 datetime string
  company: CompanyInfo;
  market_data: MarketData;
  price_history: PriceHistory;
  news: NewsCollection;
  sentiment: SentimentResult;
  events: EventsResult;
  insights: InsightsResult;
  data_sources: DataSource[];
  schema_version: string;
  completeness: 'complete' | 'partial' | 'minimal';
  partial_data_notices: string[];
  error_notices: string[];
  content_hash: string | null;
}

// ─── System metrics (GET /api/v1/metrics) ────────────────────────────────────

export interface SystemMetrics {
  window_hours: number;
  bucket_count: number;
  buckets: Record<string, unknown>[];
}

// ─── Analyze response (POST /api/v1/analyze) ────────────────────────────────

export interface AnalyzeResponse {
  run_id: string;
  status: string;
}
