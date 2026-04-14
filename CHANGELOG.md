# Changelog

All notable changes to StockLens AI are documented in this file.

This file follows the [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) format.
Versioning adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] — 2026-04-14

Phase 1 release — full end-to-end AI-powered stock analysis pipeline, developer REST API,
Next.js frontend with Server-Sent Events streaming, local LLM inference via Ollama, and
production-grade observability and security hardening.

### Added

#### Analysis Pipeline Engine (9 Steps)

- **Step 1 — TickerValidator**: resolves ticker symbols against Yahoo Finance; halts pipeline
  on unresolvable tickers (critical step); Redis idempotency prevents duplicate concurrent runs.
- **Step 2 — MarketDataCollector**: fetches real-time price, trading volume, market cap, P/E
  ratio, and OHLCV history via the `HybridMarketDataProvider`; intelligent multi-source
  fallback chain (Alpha Vantage → NSE → YFinance) with market-aware routing (Indian vs.
  global); 5-minute Redis cache keyed per ticker; non-blocking executor pattern prevents
  event loop blocking.
- **Step 3 — NewsRetriever**: retrieves articles from RSS feeds (Google Finance, Yahoo Finance)
  for the resolved company name; bounded to `MAX_ARTICLES=20` by recency + relevance ranking.
- **Step 4 — NewsDeduplicator**: removes near-duplicate headlines using SimHash (4-gram
  tokenisation, Hamming distance ≤ 3); cosine-similarity fallback; deterministic output order.
- **Step 5 — ArticleSummarizer**: per-article LLM inference (Mistral 7B); structured JSON
  output with `summary` and `topic_tags`; `asyncio.gather` parallelism across articles;
  3 concurrent LLM slots governed by semaphore.
- **Step 6 — SentimentClassifier**: per-article LLM sentiment classification
  (`positive | neutral | negative`); sentiment distribution always sums to exactly 100
  (rounding invariant enforced via largest-remainder algorithm).
- **Step 7 — EventExtractor**: bulk LLM prompt over all article summaries; returns structured
  list of corporate events (earnings, M&A, regulatory, product launches).
- **Step 8 — InsightGenerator**: full-context LLM prompt (market data + sentiment + events);
  returns structured insight sections (bull case, bear case, key risks, outlook).
- **Step 9 — ReportAssembler**: merges all step outputs into a canonical `AnalysisReport`
  domain object; assigns `completeness` level (`full | partial | minimal`) based on which
  steps succeeded; persists assembled report to PostgreSQL; emits `pipeline_complete` terminal
  event over Redis Pub/Sub.

#### Pipeline Orchestration Infrastructure

- `PipelineContext` — immutable-by-contract dataclass; sole communication channel between
  steps; carries `run_id`, `ticker`, raw step outputs, metadata, and `LLMProvider` reference.
- `PipelineOrchestrator` — sequential step executor with per-step try/except; supports
  `critical=True` early-halt; exponential-backoff retry for `is_retryable` errors;
  asyncio watchdog cancels pipelines exceeding **90 seconds** and emits `pipeline_timeout`.
- `RedisEventBus` — dual-write on every event: Redis Pub/Sub channel for live delivery +
  Redis List for reconnect replay; all keys TTL-capped at 1 hour.
- `PipelineStep` Protocol — structural subtyping interface (`execute(context) → StepResult`);
  all 9 steps implement this contract with zero coupling to orchestration code.
- `StepResult` — typed dataclass carrying `data`, `latency_ms`, `success`, and optional
  `failure_reason`; immutable after construction.

#### LLM Integration

- **OllamaProvider** — local LLM inference via `http://ollama:11434/api/generate`;
  default model `mistral:7b-instruct`; streaming=false for structured tasks.
- **OpenAIProvider** — optional per-request external inference; API key accepted as
  `X-OpenAI-Key` request header; key held in request scope only, never persisted;
  falls back to Ollama on HTTP 401.
- **NvidiaProvider** — NVIDIA NIM hosted API (`https://integrate.api.nvidia.com/v1`);
  OpenAI-compatible request schema; three free-tier models supported via `X-LLM-Provider`
  request header: `nvidia-llama` (`meta/llama-3.1-8b-instruct`), `nvidia-mistral`
  (`mistralai/mistral-7b-instruct-v0.3`), `nvidia-deepseek`
  (`deepseek-ai/deepseek-r1-distill-llama-8b`); NVIDIA API key loaded from
  `NVIDIA_API_KEY` environment variable; HTTP 401 → non-retryable error;
  HTTP 429 → retryable error with exponential backoff.
- **PromptLoader** — Jinja2 template loader; all prompt text lives in version-controlled
  `.j2` template files; zero prompt strings in step implementation code.
- **`extract_json` LLM output parser** — three-strategy fallback: (1) direct `json.loads`;
  (2) markdown-fence extraction; (3) regex `{...}` / `[...]` boundary detection; raises
  `LLMParseError` on truncated or malformed JSON after all strategies exhausted.
- **Corrective retry** — on first `LLMParseError`, re-submits the prompt with an explicit
  correction instruction; second failure marks the step as non-critical failure.

#### REST API (5 Endpoints)

- `POST /api/v1/analyze` — accepts `{ ticker }` (+ optional `X-OpenAI-Key`); validates
  ticker format `^[A-Z]{1,5}(\.[A-Z]{1,3})?$`; returns `202 { run_id, status }`.
- `GET /api/v1/analyze/stream/{run_id}` — SSE endpoint; replays buffered events on
  reconnect (via Redis List); auto-closes on `pipeline_complete` or `pipeline_failed`.
- `GET /api/v1/results/{run_id}` — returns full assembled `AnalysisReport` JSON from
  PostgreSQL; 404 if run_id unknown.
- `GET /api/v1/news/{ticker}` — returns the deduplicated article list for the most recent
  run matching the given ticker.
- `GET /api/v1/metrics` — returns system-level aggregates (pipeline counts, latency p50/p95,
  step error rates, LLM inference durations) from the `system_metrics` table.
- `GET /health` — liveness + readiness check for PostgreSQL and Redis; returns `503` if
  either dependency is down; Ollama status is informational only.

#### Frontend (Next.js 14 + React 18)

- **Zustand store** — typed slices: `AnalysisSlice` (run state, SSE events), `SettingsSlice`
  (model selection, OpenAI key in-memory only); store is not persisted to `localStorage`.
- **`useSSEStream` hook** — opens `EventSource`, dispatches typed events to Zustand, handles
  reconnect with `Last-Event-ID`, tears down on component unmount.
- **`useAnalysis` hook** — wraps `POST /api/v1/analyze` + `useSSEStream`; exposes
  `{ startAnalysis, isLoading, runId, panels, error }`.
- **8 Report Panels** — progressively revealed as step events arrive: Stock Overview,
  Price Chart (Recharts, SSR-disabled), News Feed, Sentiment Distribution (pie chart),
  Corporate Events, AI Insights, Reasoning Viewer, Data Sources footer.
- **Loading skeletons** — every panel displays an animated skeleton before its data arrives.
- **Error states** — per-panel error banners with non-technical copy for each failure mode.
- **Settings Modal** — masked `<input type="password">` for OpenAI key; key cleared on
  modal close and never written to storage; model selector supporting all 5 provider
  options: Ollama (local), OpenAI, NVIDIA LLaMA, NVIDIA Mistral, NVIDIA DeepSeek.
- **API Docs page** (`/docs`) — static page rendering all 5 endpoint definitions.
- **Non-financial-advice disclaimer** — persistent banner in `role="banner"` element,
  visible in initial viewport without scrolling.

#### Accessibility (WCAG 2.1 AA)

- Zero `axe-core` violations on the playground page (verified by Playwright + axe).
- Accessible data table alternative for the price chart (screen-reader navigable `<table>`).
- All interactive elements have descriptive `aria-label` attributes.
- Keyboard-navigable Settings Modal with focus trap and `Escape` key dismissal.
- Colour contrast ratios meet 4.5:1 minimum for all text.

#### Security Hardening

- Redis sliding-window rate limiter — 10 requests per 60-second window per IP address;
  LUA script atomic increment; `429` response with `Retry-After` header.
- Input validation — ticker format enforced by Pydantic regex at API boundary; Jinja2
  autoescape enabled for HTML contexts; all SQL via parameterised asyncpg queries.
- `structlog` log scrubber processor — redacts `openai_key`, `api_key`, and
  `authorization` fields from all structured log records before emission.
- Nginx security headers — `Content-Security-Policy`, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Strict-Transport-Security` (HSTS, max-age 1 year).
- Database least-privilege — application user `stocklens_app` holds only `SELECT`,
  `INSERT`, `UPDATE`, `DELETE` on named tables; DDL execution blocked.
- OpenAI key isolation — key accepted in `X-OpenAI-Key` request header only; never
  logged, cached, or written to any storage layer.

#### Observability and Monitoring

- **Prometheus** — `prometheus_fastapi_instrumentator` mounted on `/metrics` (internal only);
  custom metrics: `pipeline_runs_total`, `pipeline_duration_seconds`,
  `step_duration_seconds{step_name}`, `llm_inference_duration_seconds{provider}`,
  `rate_limit_rejections_total`, `active_sse_connections`.
- **Grafana** — pre-built dashboard JSON (pipeline latency percentiles, step error rates,
  LLM inference durations, SSE connection gauge).
- **Loki + Promtail** — Docker stdout log shipping; structured JSON logs searchable by
  `run_id`, `step_name`, `ticker`.
- **structlog** — JSON log format with standard fields on every record: `timestamp`, `level`,
  `run_id`, `step_name`, `ticker`, `latency_ms`, `service=stocklens-api`.

#### Backup System

- Automated encrypted backup script (`scripts/backup.sh`): `pg_dump` → gzip → AES-256
  encryption via `openssl`; writes manifest JSON with SHA-256 checksum.
- Restore script (`scripts/restore.sh`): decrypts, decompresses, restores to target DB,
  runs `validate_restore.py` integrity check.
- Backup files named with ISO 8601 timestamp; configurable `BACKUP_RETENTION_DAYS`.

#### Infrastructure

- **Docker Compose** (`infra/docker-compose.yml`) — 9 services: `api`, `frontend`, `db`
  (PostgreSQL 15), `redis` (Redis 7), `ollama`, `nginx`, `prometheus`, `grafana`, `loki`;
  all with health checks and `depends_on: condition: service_healthy`.
- **Multi-stage Dockerfiles** — `backend/Dockerfile` (base / development / builder /
  production targets); production image runs as non-root user `stocklens`.
- **Alembic migrations** — 5 tables: `analysis_runs`, `pipeline_steps`, `ticker_cache`,
  `news_cache`, `system_metrics`; all migrations reversible (`upgrade` + `downgrade`);
  `llm_provider` column CHECK constraint includes `'nvidia'` alongside `'ollama'` and `'openai'`.
- **HybridMarketDataProvider** — multi-source market data with market-aware routing:
  global stocks use Alpha Vantage (primary) → YFinance (fallback); Indian stocks
  (`.NS` / `.BO` suffix, or Redis symbol set lookup) use Alpha Vantage → NSE API →
  YFinance; Redis symbol sets (`symbols:india`, `symbols:global`) cache classification
  results after first resolution.
- **GitHub Actions CI** — lint, type-check, unit-test, integration-test, and
  production-deploy jobs; `pip-audit` and `npm audit` security gates.

---

## [Unreleased]

_No unreleased changes._

---

[1.0.0]: https://github.com/govindp47/stocklens-ai/releases/tag/v1.0.0
