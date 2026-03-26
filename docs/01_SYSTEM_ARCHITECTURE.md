# 01_SYSTEM_ARCHITECTURE.md — StockLens AI

---

## 1. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CLIENT LAYER                                     │
│                                                                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │  Next.js SPA (React 18)                                              │  │
│  │                                                                      │  │
│  │  ┌───────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │  │
│  │  │ Ticker    │  │ Reasoning    │  │ Report Panel │  │ Settings  │  │  │
│  │  │ Input     │  │ Viewer       │  │ Grid         │  │ Modal     │  │  │
│  │  └───────────┘  └──────────────┘  └──────────────┘  └───────────┘  │  │
│  │                                                                      │  │
│  │  SSE Consumer ←─── /api/v1/analyze/stream/{run_id}                  │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │  HTTPS
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          API GATEWAY / REVERSE PROXY                        │
│                    Nginx (SSL termination, rate limiting)                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER (FastAPI)                         │
│                                                                             │
│  ┌──────────────────┐  ┌────────────────────┐  ┌──────────────────────┐   │
│  │  REST API Router │  │  SSE Stream Router  │  │  Background Worker   │   │
│  │  /api/v1/...     │  │  /api/v1/analyze/  │  │  (pipeline executor) │   │
│  │                  │  │   stream/{run_id}   │  │                      │   │
│  └──────────────────┘  └────────────────────┘  └──────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     ANALYSIS PIPELINE ENGINE                        │   │
│  │                                                                     │   │
│  │  Step 1: TickerValidator    Step 2: MarketDataCollector             │   │
│  │  Step 3: NewsRetriever      Step 4: NewsDeduplicator                │   │
│  │  Step 5: ArticleSummarizer  Step 6: SentimentClassifier             │   │
│  │  Step 7: EventExtractor     Step 8: InsightGenerator                │   │
│  │  Step 9: ReportAssembler                                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
       │                  │                   │                 │
       ▼                  ▼                   ▼                 ▼
┌──────────┐    ┌──────────────────┐   ┌──────────┐   ┌──────────────────┐
│ PostgreSQL│   │  Redis           │   │  Ollama  │   │ External APIs    │
│ (results │   │  (rate limiting, │   │  (Local  │   │                  │
│  store)  │   │   SSE pub/sub,   │   │  LLM:    │   │ Yahoo Finance    │
│          │   │   idempotency)   │   │  Mistral │   │ RSS/News Feeds   │
│          │   │                  │   │  7B)     │   │ OpenAI (opt.)    │
└──────────┘   └──────────────────┘   └──────────┘   └──────────────────┘
```

---

## 2. System Component Breakdown

### 2.1 Client Layer

**Next.js SPA**

- Responsibility: Render the entire playground UI, consume the SSE stream from the backend, progressively reveal report panels as pipeline step events arrive, manage session-scoped OpenAI key state in memory only.
- Communication: HTTPS REST for triggering analysis (`POST /api/v1/analyze`), HTTPS SSE for consuming pipeline events (`GET /api/v1/analyze/stream/{run_id}`).
- State: All application state is held in React component state (Zustand store). Nothing is written to `localStorage` or `sessionStorage` except optionally the user's OpenAI key keyed under a session-scoped in-memory variable that is never flushed to disk.

**Settings Modal**

- Responsibility: Accept and validate the format of an OpenAI API key in a masked `<input type="password">` field. Store it only in memory (React state or Zustand slice). Clear it on page unload. Never transmit it to the backend except as a per-request header on analysis calls.

### 2.2 API Gateway / Reverse Proxy

**Nginx**

- Responsibility: SSL/TLS termination, static asset serving, upstream proxying to FastAPI workers, IP-level rate limiting (via `limit_req_zone`), request logging (access log forwarded to Loki or stdout for Docker log collection).
- Configuration: Separate `upstream` blocks for the FastAPI app and for the Next.js SSR server. `/api/v1/*` is proxied to FastAPI. `/_next/*` and `/*` are proxied to Next.js.

### 2.3 Application Layer

**FastAPI Application (Python 3.11+)**

- Responsibility: Receive analysis requests, generate a run identifier, enqueue the pipeline for async execution in a background task, return the run identifier to the client immediately (`202 Accepted`), expose the SSE stream endpoint that publishes step events as the background task progresses.
- Process model: Single Uvicorn process with `asyncio` event loop. Pipeline steps that are I/O-bound (HTTP calls to data providers, HTTP calls to Ollama) are awaited natively. CPU-bound steps (deduplication hashing, report assembly) run inline but are fast enough to not block; if profiling shows blocking, they move to a `ProcessPoolExecutor`.
- Concurrency: Multiple concurrent pipeline runs are supported because each run is an independent `asyncio` task. The shared resources (Redis, PostgreSQL connection pool) use async drivers (`asyncpg`, `aioredis`).

**Background Worker (asyncio task)**

- Responsibility: Execute the 9-step pipeline sequentially for a given `run_id`. After each step, publish a step-event message to a Redis Pub/Sub channel keyed by `run_id`. Write the final assembled report to PostgreSQL.

**SSE Stream Router**

- Responsibility: Subscribe to the Redis Pub/Sub channel for a given `run_id`, relay messages to the client over SSE. Handle client disconnect by unsubscribing. If the client reconnects, replay missed events from a Redis list (append-only log per `run_id`, TTL-capped).

### 2.4 Analysis Pipeline Engine

Each pipeline step is implemented as an independent, injectable class with a uniform interface:

```
class PipelineStep(Protocol):
    async def execute(self, context: PipelineContext) -> StepResult:
        ...
```

`PipelineContext` is a mutable dataclass passed through all steps. Each step reads from it and writes its output back into it. Steps are registered in an ordered list in the `PipelineOrchestrator`. The orchestrator catches per-step exceptions, marks the step as failed in the context, emits a failure event, and continues to the next step (unless the step is marked `critical=True`, in which case it halts and emits a terminal failure event).

### 2.5 Data Layer

**PostgreSQL 15**

- Stores: completed analysis run records, assembled report JSON, step-level execution metadata, and system metrics aggregates.
- Used only for: persisting completed or failed run results for the past-results API endpoint, and for aggregating metrics.
- Connection pool: `asyncpg` with a pool size of 5–10 connections for MVP.

**Redis 7**

- Stores: step-event messages per `run_id` (as a Redis List for replay + Pub/Sub for live delivery), rate-limit counters (IP-keyed, sliding window), idempotency keys for pipeline deduplication, and pipeline in-progress flags.
- All keys are TTL-scoped: step event lists expire after 1 hour, rate-limit counters expire per their window, run in-progress flags expire after 2 minutes.

### 2.6 LLM Layer

**Ollama (Local)**

- Runs as a sidecar process on the same host or within the same Docker Compose network.
- Hosts: `mistral:7b-instruct` (default) or `llama3:8b-instruct` as a fallback.
- Accessed via `http://ollama:11434/api/generate` (POST, streaming=false for structured tasks; streaming=true for insight generation to enable token streaming if desired in future).
- Prompt templates are managed as version-controlled Jinja2 template files, one per pipeline step that invokes inference.

**OpenAI (Optional, Per-Request)**

- The client passes the user's API key as a custom request header (`X-OpenAI-Key`) only on the `POST /api/v1/analyze` call.
- The backend holds this key in the request scope only. It is never written to any storage layer.
- The `LLMProvider` abstraction selects between `OllamaProvider` and `OpenAIProvider` at request time.

---

## 3. Clean Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│  Presentation Layer                                     │
│  FastAPI routers, request/response models (Pydantic),   │
│  SSE event serialization, HTTP error handlers           │
├─────────────────────────────────────────────────────────┤
│  Application Layer                                      │
│  PipelineOrchestrator, use-case handlers                │
│  (AnalyzeTickerUseCase, GetPastResultUseCase, etc.)      │
├─────────────────────────────────────────────────────────┤
│  Domain Layer                                           │
│  PipelineContext, StepResult, AnalysisReport,           │
│  domain events, business rules (validation, dedup,      │
│  sentiment thresholds, step criticality definitions)    │
├─────────────────────────────────────────────────────────┤
│  Infrastructure Layer                                   │
│  MarketDataProvider (yfinance adapter),                 │
│  NewsProvider (RSS/feed adapter),                       │
│  LLMProvider (Ollama + OpenAI adapters),                │
│  ReportRepository (asyncpg adapter),                    │
│  EventBus (Redis Pub/Sub adapter),                      │
│  RateLimiter (Redis sliding-window adapter)             │
└─────────────────────────────────────────────────────────┘
```

Dependencies point inward only. The domain layer has zero imports from infrastructure or presentation. Infrastructure adapters implement interfaces defined in the domain layer (Dependency Inversion).

---

## 4. Module Boundaries

| Module | Owns | Does NOT touch |
|---|---|---|
| `api` | HTTP request routing, response serialization, auth headers | Pipeline logic, DB queries |
| `pipeline` | Orchestration, step execution order, context lifecycle | HTTP transport, DB writes |
| `steps` | Individual step implementations | Orchestration, SSE delivery |
| `providers.market_data` | yfinance HTTP calls, response normalization | LLM, news, storage |
| `providers.news` | RSS/feed HTTP calls, deduplication algorithms | LLM, market data, storage |
| `providers.llm` | Prompt rendering, LLM HTTP calls, output parsing | News, market data, storage |
| `repositories` | SQL queries, asyncpg cursor management | Pipeline logic, HTTP |
| `events` | Redis Pub/Sub publish/subscribe | Pipeline logic, HTTP |
| `rate_limiter` | Redis sliding-window increment/check | Pipeline logic, routing |

---

## 5. Data Flow Lifecycle

```
[User Browser]
     │
     │ POST /api/v1/analyze  { ticker, x-openai-key? }
     ▼
[FastAPI: AnalyzeRouter]
     │ validate ticker format (regex)
     │ check rate limit (Redis)  → 429 if exceeded
     │ generate run_id (UUID4)
     │ check idempotency key (Redis) → return existing run_id if duplicate in-flight
     │ set run in-progress flag (Redis, TTL=120s)
     │ launch asyncio background task: pipeline.run(run_id, ticker, llm_key?)
     │
     ├─ return 202 { run_id }
     ▼
[Browser: GET /api/v1/analyze/stream/{run_id}]  ← SSE connection
     │
[FastAPI: SSERouter subscribes to Redis channel: pipeline:events:{run_id}]

[Background Task: PipelineOrchestrator]
     │
     ├─ Step 1: TickerValidator
     │     validate ticker against exchange resolver (yfinance lookup)
     │     → publish step_event{ step=1, status=complete, data={company, exchange, sector} }
     │
     ├─ Step 2: MarketDataCollector
     │     fetch price, change, volume, mktcap, ratios, OHLCV history
     │     → publish step_event{ step=2, status=complete, data={...} }
     │
     ├─ Step 3: NewsRetriever
     │     fetch RSS feed(s) for ticker+company name
     │     → publish step_event{ step=3, status=complete, data={articles:[...]} }
     │
     ├─ Step 4: NewsDeduplicator
     │     cosine similarity / SimHash dedup on headlines
     │     → publish step_event{ step=4, status=complete, data={articles:[...deduplicated]} }
     │
     ├─ Step 5: ArticleSummarizer
     │     for each article: prompt LLM → summary + topic tags
     │     → publish step_event{ step=5, status=complete, data={summaries:[...]} }
     │
     ├─ Step 6: SentimentClassifier
     │     for each article: prompt LLM → {positive|neutral|negative}
     │     aggregate distribution
     │     → publish step_event{ step=6, status=complete, data={distribution, dominant} }
     │
     ├─ Step 7: EventExtractor
     │     prompt LLM with all articles → extract structured events
     │     → publish step_event{ step=7, status=complete, data={events:[...]} }
     │
     ├─ Step 8: InsightGenerator
     │     prompt LLM with full context → structured insight sections
     │     → publish step_event{ step=8, status=complete, data={insight_sections} }
     │
     ├─ Step 9: ReportAssembler
     │     merge all step outputs → AnalysisReport domain object
     │     persist to PostgreSQL
     │     → publish step_event{ step=9, status=complete, data={report_summary} }
     │     → publish pipeline_event{ status=complete, run_id }
     │
[SSERouter relays all events to browser]
[Browser progressively renders each panel as its step_event arrives]
```

---

## 6. Request / Command Processing Pipeline

### 6.1 Analysis Request Entry

1. `POST /api/v1/analyze` received by `AnalyzeRouter`.
2. Pydantic model `AnalyzeRequest` validates: ticker format (`^[A-Z]{1,5}(\.[A-Z]{1,3})?$`), max length 12. If invalid, return `422 Unprocessable Entity` with structured field errors.
3. Rate limit check: `RateLimiter.check(ip_address, window=60s, limit=10)`. On exceed: `429` with `Retry-After` header.
4. Idempotency check: `Redis.get(f"idem:{ip}:{ticker}")`. If present and run still in-progress, return `202 { run_id: existing }`. This prevents duplicate pipeline launches from double-clicks or retries.
5. `run_id = uuid4()`. Store `idem:{ip}:{ticker}` → `run_id` with TTL 120s.
6. Store `run:inprogress:{run_id}` → `"1"` with TTL 120s.
7. Launch `asyncio.create_task(orchestrator.run(run_id, ticker, llm_key))`.
8. Return `202 { run_id, status: "accepted" }`.

### 6.2 SSE Stream Entry

1. `GET /api/v1/analyze/stream/{run_id}` received by `SSERouter`.
2. Validate `run_id` is a valid UUID4.
3. Check `run:inprogress:{run_id}` or `run:complete:{run_id}` in Redis — if neither exists, return `404`.
4. Fetch replay buffer: `LRANGE pipeline:events:{run_id} 0 -1` — send all buffered events to client immediately (handles reconnects).
5. Subscribe to `pipeline:events:{run_id}` Pub/Sub channel.
6. Stream events as SSE `data:` messages (JSON-serialized `StepEvent`).
7. On `pipeline_complete` or `pipeline_failed` terminal event, send the event and close the stream.
8. On client disconnect, unsubscribe and release the Pub/Sub connection.

---

## 7. Concurrency Model

**Design:** Cooperative multitasking via Python `asyncio`. All I/O is async (HTTP calls to yfinance, news feeds, Ollama, Redis, PostgreSQL). No threading is used for pipeline steps.

**Concurrent analysis runs:** Each `asyncio.create_task(...)` is an independent coroutine. FastAPI's Uvicorn event loop handles multiple concurrent runs without interference because all awaits yield control cooperatively.

**Bottleneck: LLM inference.** Ollama processes requests serially on a single GPU/CPU context. Concurrent LLM calls queue at the Ollama server. To prevent starvation:

- A `asyncio.Semaphore(max_concurrent_llm_calls=3)` governs LLM access across all in-flight pipelines. This ensures at most 3 LLM calls are in-flight simultaneously per Ollama instance.
- If the semaphore is not acquired within 30s, the step fails gracefully.

**Redis Pub/Sub concurrency:** Each SSE connection holds one async Redis subscriber. The `aioredis` client pool ensures connections are not exhausted; pool size is configured to `max_sse_connections + 5` buffer.

**Resource isolation per run:** Each run has its own `PipelineContext` object. No shared mutable state exists between runs. Read-only configuration (prompt templates, threshold values) is shared safely.

---

## 8. Failure Recovery Model

### Step-Level Failure

Each step is wrapped in a try/except block in the `PipelineOrchestrator`:

```python
try:
    result = await step.execute(context)
    context.record_success(step)
    await event_bus.publish(run_id, StepEvent(step=step.name, status="complete", data=result))
except ExternalProviderError as e:
    context.record_failure(step, reason=str(e))
    await event_bus.publish(run_id, StepEvent(step=step.name, status="failed", reason=str(e)))
    if step.critical:
        await event_bus.publish(run_id, PipelineEvent(status="failed", reason=str(e)))
        return
    # non-critical: continue to next step
```

### Critical vs. Non-Critical Steps

| Step | Critical | Rationale |
|---|---|---|
| TickerValidator | YES | Cannot proceed without resolving the ticker to a company |
| MarketDataCollector | NO | Report can still show news/insights without price data |
| NewsRetriever | NO | Report can show market data without news |
| NewsDeduplicator | NO | Undeduplicated articles are acceptable degraded output |
| ArticleSummarizer | NO | Headlines still display without summaries |
| SentimentClassifier | NO | Sentiment panel shows unavailable notice |
| EventExtractor | NO | Events panel shows unavailable notice |
| InsightGenerator | NO | Insight panel shows failure notice |
| ReportAssembler | YES | Without assembly, nothing can be persisted or delivered |

### Pipeline-Level Failure

If the `asyncio.Task` itself raises an uncaught exception (programming error), the task's done callback writes a terminal `pipeline_failed` event to Redis and marks the run as failed in PostgreSQL.

### Timeout Handling

Each individual HTTP call to external providers uses `httpx.AsyncClient` with:

- `connect_timeout=5s`
- `read_timeout=15s` (market data / news)
- `read_timeout=45s` (LLM inference steps)

If a timeout fires, the step raises `ExternalProviderError`, which follows the non-critical failure path above. The pipeline does not hang indefinitely.

A global pipeline timeout watchdog task is created alongside the pipeline task: if the pipeline has not completed within 90 seconds, the watchdog cancels it and emits a `pipeline_timeout` event.

### Database Write Failure on Report Assembly

If the PostgreSQL write fails during ReportAssembler, the step logs the error, publishes a `step_failed` event, but the SSE stream has already delivered all data to the client — the user has seen the report. The only consequence is that the `GET /past-results` endpoint will not find this run. This is an acceptable degradation for MVP.

---

## 9. Observability Strategy

### Structured Logging

- All log records are emitted as JSON using `structlog`.
- Standard fields on every log record: `timestamp`, `level`, `run_id` (if in pipeline context), `step_name` (if in step context), `ticker` (if in run context), `latency_ms` (for I/O operations), `service=stocklens-api`.
- Sensitive fields: `openai_key` is NEVER logged. If the key is present, log `openai_key_present=true` only.
- Log levels: `DEBUG` for step-internal details (dev only), `INFO` for step lifecycle events, `WARNING` for non-critical step failures, `ERROR` for critical failures and unhandled exceptions.

### Metrics

- `prometheus_fastapi_instrumentator` is mounted on the FastAPI app to expose `/metrics`.
- Custom counters and histograms:
  - `pipeline_runs_total{status=complete|failed|timeout}` — counter
  - `pipeline_duration_seconds{ticker_type=known|unknown}` — histogram (P50, P95, P99)
  - `step_duration_seconds{step_name}` — histogram per step
  - `llm_inference_duration_seconds{provider=ollama|openai, step_name}` — histogram
  - `external_provider_errors_total{provider=yfinance|rss|ollama|openai}` — counter
  - `rate_limit_rejections_total` — counter
  - `active_sse_connections` — gauge
- Prometheus scrape endpoint: `GET /metrics` (internal only, not exposed via Nginx to public).

### Tracing

- OpenTelemetry SDK with OTLP exporter configured (Jaeger for dev, configurable collector endpoint for prod).
- A `trace_id` is injected into each request at the FastAPI middleware layer and propagated through all async tasks.
- Each pipeline step creates a child span.

### Dashboards

- Grafana with Prometheus data source for latency percentiles, error rates, and step failure distributions.
- Loki for log aggregation (stdout from Docker containers shipped via Promtail or Alloy).

---

## 10. Performance Strategy

### P50 / P95 Pipeline Latency Targets

| Phase | P50 | P95 |
|---|---|---|
| Time-to-first-panel (Steps 1–2) | 3s | 8s |
| Time-to-news-panel (Steps 3–4) | 8s | 15s |
| Time-to-full-report (Steps 1–9) | 35s | 60s |

### Optimization Levers

1. **Parallelism within the news processing phase:** Steps 5 (summarization) and 6 (sentiment) can process articles concurrently using `asyncio.gather`. Each article's summarization and sentiment classification are independent. With 10 articles and 3 parallel LLM calls allowed by the semaphore, 10 articles process in roughly ⌈10/3⌉ = 4 LLM batches rather than 10 serial calls.

2. **Market data and news retrieval parallelism:** Steps 2 (market data) and 3 (news retrieval) are independent of each other. They execute concurrently using `asyncio.gather` after step 1 (ticker validation) completes.

3. **Prompt engineering for inference speed:** Prompts are designed to elicit structured JSON output from the LLM (shorter, parseable responses). This reduces token generation time compared to open-ended prose generation.

4. **yfinance caching:** Market data for the same ticker within a 5-minute window is served from Redis cache (TTL=300s). This eliminates redundant external HTTP calls for popular tickers analyzed in quick succession.

5. **Connection pooling:** Both `asyncpg` (PostgreSQL) and `aioredis` (Redis) use persistent connection pools initialized at application startup. No per-request connection establishment overhead.

---

## 11. Scaling Considerations

### MVP (Single-Server)

- FastAPI + Uvicorn runs as a single process on a single VM.
- Ollama runs on the same host (shared CPU/GPU).
- PostgreSQL and Redis run as Docker containers on the same host.
- This architecture is sufficient for portfolio/demo traffic (estimated < 50 concurrent users).

### Scale-Out Path (Phase 2+)

- **FastAPI:** Run multiple Uvicorn workers behind Gunicorn, or scale horizontally with multiple containers behind the Nginx upstream. SSE streams require sticky sessions (or move to a Redis-backed SSE relay pattern, which the current architecture already supports since all events flow through Redis Pub/Sub).
- **Ollama:** Move to a dedicated Ollama host with GPU. FastAPI containers point to the Ollama host via environment variable. Alternatively, use `vllm` for higher-throughput inference.
- **PostgreSQL:** Move to a managed PostgreSQL instance (e.g., RDS, Supabase) for automatic backups and failover.
- **Redis:** Move to a managed Redis cluster (ElastiCache, Upstash) for high-availability Pub/Sub.
- **Rate limiting:** Nginx `limit_req` is sufficient for MVP. At scale, move to Redis-based rate limiting with `slowapi` (already in place in the application layer) and remove Nginx-level limiting.

### Large Dataset Handling

- News articles per analysis run: bounded to a configurable maximum (default: `MAX_ARTICLES=20`). If more articles are retrieved from RSS feeds, they are ranked by recency and relevance, and only the top `MAX_ARTICLES` are processed through LLM steps.
- Historical price data: fetched for a maximum of 365 calendar days. The OHLCV response is stored as a JSON array in the report; no separate time-series table is needed for MVP.
- PostgreSQL report rows are purged by a scheduled cleanup job (see Section 13 below) after a configurable TTL (default: 24 hours), ensuring the `analysis_runs` table does not grow unboundedly.

---

## 12. Background Job Architecture

### Pipeline Execution Task

- Launched as `asyncio.create_task(...)` inline in the request handler. This is a short-lived task (< 90s). No external job queue (Celery, RQ) is required for MVP.
- Task lifecycle: created → running → complete | failed | timed-out.
- Completion is tracked via Redis (`run:complete:{run_id}` with TTL 1h) and PostgreSQL (`analysis_runs.status`).

### Cleanup Job

- A repeating background task (`asyncio.create_task` with infinite loop + `asyncio.sleep(3600)`) runs hourly.
- Deletes `analysis_runs` rows where `created_at < NOW() - INTERVAL '24 hours'`.
- Cleans up orphaned Redis keys with expired TTLs (Redis handles this natively via TTL; no explicit cleanup needed).

### Metrics Aggregation Job

- A repeating background task runs every 5 minutes.
- Reads Prometheus counters/histograms and writes aggregated rows to the `system_metrics` table (used by the `GET /api/v1/metrics` endpoint to serve the system metrics API).

---

## 13. Caching Strategy

| Resource | Cache Layer | TTL | Invalidation |
|---|---|---|---|
| Market data (price, ratios, OHLCV) | Redis | 300s (5 min) | TTL-based expiry |
| Ticker resolution (company name, exchange) | Redis | 3600s (1 hr) | TTL-based expiry |
| News feed RSS responses | Redis | 300s (5 min) | TTL-based expiry |
| Completed report (for past-results API) | PostgreSQL + Redis | 24h (configurable) | Scheduled deletion job |
| LLM prompt templates | In-process dict at startup | Process lifetime | App restart |
| Prometheus metrics scrape | Prometheus | 15s scrape interval | N/A |

**Cache Key Schema:**

```
market:data:{TICKER}          → JSON string
market:resolve:{TICKER}       → JSON string (company_name, exchange, sector)
news:feed:{TICKER}:{page_hash} → JSON string (raw article list)
report:{run_id}               → JSON string (assembled report)
```

**Cache Miss Handling:** All cache reads wrap `try/except` around the Redis call. On Redis unavailability, the system falls back to the live data source. No request fails solely because Redis is unreachable.

---

## 14. Failure Scenario Matrix

| Failure | Detection | Behavior | User Impact |
|---|---|---|---|
| Redis unreachable at startup | Health check on startup | App refuses to start | Deployment failure; no user impact |
| Redis unreachable during request | `aioredis.ConnectionError` in rate-limiter | Rate limiting disabled (fail-open); request proceeds | No rate limiting; minor abuse risk |
| Redis unreachable during pipeline | Pub/Sub publish fails | Events lost; SSE stream stalls | User sees no progress; pipeline completes but no updates arrive; run is recoverable via past-results API |
| PostgreSQL unreachable during write | `asyncpg.PostgresConnectionError` | Report assembly step fails non-critically | Past-results API will not find the run; user's SSE stream still received all data |
| yfinance returns empty response | Empty dict check | MarketDataCollector marks step as no-data; continues | Stock Overview panel shows "No data available" |
| yfinance rate-limited (HTTP 429) | Status code check | Step fails; retry once after 2s; on second failure, mark step failed | Stock Overview panel shows data unavailability notice |
| RSS feed unreachable | `httpx.ConnectError` | NewsRetriever step fails; subsequent steps skip LLM on news | News, Sentiment, Events panels show unavailability notices |
| Ollama unreachable | `httpx.ConnectError` or `httpx.TimeoutException` | LLM steps (5, 6, 7, 8) all fail; non-critical | Summaries, sentiment, events, insights all unavailable; market data still shown |
| Ollama returns malformed JSON | JSON parse error | Step fails; LLM output discarded | Affected panel shows partial data notice |
| OpenAI key invalid | HTTP 401 from OpenAI | LLMProvider falls back to Ollama; user notified via step event | Analysis proceeds with local model |
| Pipeline global timeout (>90s) | Watchdog task | Pipeline task cancelled; terminal event emitted | User sees timeout banner; can resubmit |
| Unhandled exception in step | Task exception handler | Step marked failed; pipeline halted if critical | Depends on step criticality (see Section 8) |
| Duplicate concurrent submission | Idempotency key in Redis | Existing `run_id` returned | User's browser reconnects to existing run stream |
