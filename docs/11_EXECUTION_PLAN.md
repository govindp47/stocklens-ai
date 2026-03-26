# 11_EXECUTION_PLAN.md — StockLens AI

---

## 1. Execution Philosophy

The execution plan is structured as five sequential engineering phases, each producing a deployable, testable increment. No phase begins until the previous phase's exit criteria are met. Each phase is estimated for a solo engineer or a two-person team working at focused capacity.

**Principles:**

- Each phase ends with something runnable — not a partial skeleton.
- Infrastructure is stood up first, before features, to eliminate late-stage integration surprises.
- The domain engine (pipeline) is built and verified before the UI is wired to it.
- External dependencies (yfinance, Ollama, RSS) are integrated one at a time with fallbacks confirmed before the next dependency is added.

---

## 2. Phase Overview

```
Phase 1: Infrastructure Foundation           (Week 1–2)
Phase 2: Core Pipeline — Market Data + News  (Week 2–4)
Phase 3: AI Analysis Pipeline                (Week 4–6)
Phase 4: Frontend + Full Integration         (Week 6–9)
Phase 5: Production Hardening + Launch       (Week 9–11)
```

Total estimated duration for a solo engineer working full-time: **10–11 weeks**.
For a two-person team: **6–7 weeks** (backend and frontend can parallelize from Phase 3 onward).

---

## 3. Phase 1 — Infrastructure Foundation

**Duration:** 8–10 working days

### Scope

- Repository structure and tooling configuration.
- Docker Compose local development stack (PostgreSQL, Redis, Ollama, Nginx).
- FastAPI application scaffold with lifespan, health check, and Prometheus instrumentation.
- Next.js application scaffold with layout, global styles, Tailwind, and shadcn/ui.
- Database schema (all five tables) applied via Alembic initial migration.
- CI pipeline: lint, type-check, and unit test jobs (no tests yet — scaffold only).
- `Makefile` developer commands.
- Structured logging with `structlog`.

### Deliverables

- `docker compose up` starts all services with no errors.
- `GET /health` returns `{"status": "healthy"}` with DB and Redis checks passing.
- `GET /` serves the Next.js landing page with a static ticker input (no backend wiring).
- Alembic `upgrade head` creates all five tables with constraints and indexes.
- GitHub Actions CI runs `ruff`, `mypy`, `eslint`, `tsc` on every push.

### Dependencies

- None. This is the foundational phase.

### Complexity

- Low-to-medium. The risk is in Docker networking and Ollama model pull time on first setup.

### Engineering Effort Estimate

| Task | Days |
|---|---|
| Repo structure, `pyproject.toml`, `package.json`, Makefile | 0.5 |
| Docker Compose full stack (all services, networks, volumes) | 1.5 |
| FastAPI scaffold (main, lifespan, config, health, routers stubs) | 1.5 |
| Database schema DDL + Alembic migration | 1.0 |
| Next.js scaffold (layout, globals.css, Tailwind, shadcn/ui install) | 1.0 |
| Nginx configuration (dev proxy + prod SSL template) | 0.5 |
| Structured logging setup (`structlog` + log scrubber) | 0.5 |
| Prometheus instrumentation + Grafana dashboard skeleton | 0.5 |
| CI pipeline (GitHub Actions lint/typecheck jobs) | 1.0 |
| Ollama setup (Dockerfile, model pull script, health check) | 1.0 |
| **Total** | **9.0 days** |

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Ollama model pull fails in CI (no GPU on GitHub Actions runners) | Medium | Use CPU inference in CI; skip Ollama in unit/integration test environments (all LLM calls are mocked) |
| asyncpg connection pool misconfiguration causes startup hang | Low | Set `command_timeout=10` on pool; startup fails fast and loudly |
| Next.js + Tailwind CSS variable setup friction | Low | Follow shadcn/ui setup guide exactly; tested path |

### Exit Criteria

- [ ] `make dev` starts full stack in < 60 seconds with no errors.
- [ ] `GET /health` returns 200 with all checks passing.
- [ ] `alembic upgrade head` and `alembic downgrade base` both complete without errors.
- [ ] `make lint` and `make typecheck` pass with zero warnings.
- [ ] CI pipeline passes on `main`.
- [ ] Ollama responds to `GET /api/tags` with the pulled model listed.

---

## 4. Phase 2 — Core Pipeline: Market Data and News

**Duration:** 8–10 working days

### Scope

- `PipelineContext`, `PipelineOutputs`, `PipelineStep` Protocol, `StepResult`, `StepFailure` domain objects.
- `PipelineOrchestrator` with step execution, retry logic, critical/non-critical branching, and watchdog timeout.
- `RedisEventBus` (Pub/Sub publish + List append for replay).
- Steps 1–4: `TickerValidator`, `MarketDataCollector`, `NewsRetriever`, `NewsDeduplicator`.
- `YFinanceMarketDataProvider` (run-in-executor pattern).
- `RSSNewsFeedProvider` (feedparser, relevance filter, recency filter).
- `ReportRepository` (insert run, update status, upsert step records).
- `RedisSlidingWindowRateLimiter`.
- `POST /api/v1/analyze` and `GET /api/v1/analyze/stream/{run_id}` endpoints.
- Unit tests for Steps 1–4 and the orchestrator.
- Integration test: full pipeline Steps 1–4 with mocked HTTP, DB assertions.

### Deliverables

- Submit `POST /api/v1/analyze` with `{"ticker": "AAPL"}` → receive `run_id`.
- Connect to `GET /api/v1/analyze/stream/{run_id}` → observe 4 step events arrive in real time.
- `analysis_runs` and `pipeline_steps` rows written correctly to PostgreSQL.
- Steps 1–4 fail gracefully when yfinance/RSS are mocked to return errors.
- Unit test coverage ≥ 80% for `pipeline/` and `infrastructure/providers/`.

### Dependencies

- Phase 1 complete (Docker stack, DB schema, FastAPI scaffold).
- `yfinance` installable and returning data for AAPL in manual testing.
- At least one RSS feed returning articles for AAPL in manual testing.

### Complexity

- Medium. The `asyncio`-in-executor pattern for `yfinance` is a known friction point. The Redis Pub/Sub + List dual-write pattern requires careful ordering to guarantee replay correctness.

### Engineering Effort Estimate

| Task | Days |
|---|---|
| Domain objects: `PipelineContext`, `StepResult`, `StepFailure`, `PipelineStep` Protocol | 1.0 |
| `PipelineOrchestrator` with retry + critical halting + watchdog | 2.0 |
| `RedisEventBus` (publish to Pub/Sub + append to List) | 0.5 |
| `YFinanceMarketDataProvider` (executor, normalization, caching) | 1.5 |
| `RSSNewsFeedProvider` (feedparser, filters, dedup article IDs) | 1.5 |
| Steps 1–4 implementations | 1.5 |
| `ReportRepository` (insert, update, upsert_step) | 1.0 |
| `RedisSlidingWindowRateLimiter` | 0.5 |
| `POST /analyze` + `GET /stream/{run_id}` endpoints + idempotency | 1.5 |
| Unit tests for Steps 1–4 + orchestrator | 2.0 |
| Integration test: pipeline Steps 1–4 + SSE event order | 1.0 |
| **Total** | **14.0 days → 10 focused days** |

*Note: 14 task-days compressed to 10 working days via parallel unit test writing during provider development.*

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| yfinance returns inconsistent field names across ticker types | Medium | Defensive `dict.get()` with `None` fallback on every field; never KeyError |
| RSS feed URL format for international tickers differs | Low | Phase 1 only requires US tickers (see PRD Phase 1 scope); international is Phase 3 |
| SSE replay delivers events out of order on fast reconnect | Low | Redis List is append-only and ordered by insertion; `LRANGE 0 -1` guarantees order |
| asyncio.create_task exception not surfaced to test assertions | Medium | All pipeline tasks use a `done_callback` to log unhandled exceptions; tests `await` the task directly |

### Exit Criteria

- [ ] `POST /api/v1/analyze` with `AAPL` → 202 response with valid UUID `run_id`.
- [ ] SSE stream delivers exactly 4 step events (steps 1–4) with correct `step_index` values.
- [ ] `analysis_runs` row has `status='complete'` and `steps_completed=4` after pipeline.
- [ ] Pipeline continues (partial) when `MarketDataCollector` is mocked to fail.
- [ ] Pipeline halts (failed) when `TickerValidator` is mocked to fail.
- [ ] Rate limiter rejects the 11th request per 60s per IP with 429.
- [ ] All unit and integration tests pass with `pytest`.

---

## 5. Phase 3 — AI Analysis Pipeline

**Duration:** 8–10 working days

### Scope

- Jinja2 prompt template system (`PromptLoader`, all four `.j2` templates).
- `OllamaProvider` and `OpenAIProvider` implementations.
- LLM response parser (`extract_json`, corrective retry, Pydantic validation).
- Steps 5–9: `ArticleSummarizer`, `SentimentClassifier`, `EventExtractor`, `InsightGenerator`, `ReportAssembler`.
- Sentiment distribution rounding invariant.
- Dominant label derivation logic.
- Report completeness computation.
- `GET /api/v1/results/{run_id}` endpoint.
- `GET /api/v1/news/{ticker}` endpoint (returns articles + summaries + sentiment).
- `GET /api/v1/metrics` endpoint (reads from `system_metrics_hourly`).
- Metrics aggregation background job.
- TTL cleanup background job.
- Unit tests for Steps 5–9, LLM output parsing, all domain logic.
- Integration test: full 9-step pipeline end-to-end.

### Deliverables

- Full pipeline (`POST /analyze` → all 9 step events → assembled report in PostgreSQL).
- `GET /api/v1/results/{run_id}` returns complete JSON report.
- `GET /api/v1/news/{ticker}` returns articles with summaries and sentiment.
- `GET /api/v1/metrics` returns aggregated system metrics.
- Report is `partial` (not failed) when Ollama is mocked to return 500.
- All four API endpoints return structured JSON errors on invalid input.
- Unit test coverage ≥ 80% for all steps.

### Dependencies

- Phase 2 complete.
- Ollama running with `mistral:7b-instruct` model pulled.
- Manual smoke test: direct `curl` to Ollama `/api/generate` returns valid JSON.

### Complexity

- High. This phase contains the most domain logic: LLM output parsing with fallbacks, sentiment rounding invariant, event deduplication across articles, and report assembly from partial outputs. The interaction between the LLM semaphore and `asyncio.gather` for per-article steps requires careful implementation to avoid semaphore deadlock.

### Engineering Effort Estimate

| Task | Days |
|---|---|
| `PromptLoader` + all 4 Jinja2 prompt templates | 1.0 |
| `OllamaProvider` + `OpenAIProvider` + `LLMProvider` Protocol | 1.5 |
| `extract_json` parser + corrective retry + Pydantic LLM output models | 1.5 |
| `ArticleSummarizer` (batched asyncio.gather + semaphore) | 1.0 |
| `SentimentClassifier` (batched + distribution + rounding + dominant label) | 1.5 |
| `EventExtractor` (corpus prompt + output validation) | 1.0 |
| `InsightGenerator` (conditional context building + section validation) | 1.0 |
| `ReportAssembler` (completeness logic + notices assembly) | 1.0 |
| TTL cleanup job + metrics aggregation job | 1.0 |
| `GET /results`, `GET /news`, `GET /metrics` endpoints | 1.0 |
| Unit tests: Steps 5–9 + domain logic + LLM parse edge cases | 2.5 |
| Integration test: full 9-step pipeline, partial degradation cases | 1.5 |
| **Total** | **15.5 days → 10 focused days** |

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `mistral:7b-instruct` fails to reliably return valid JSON | Medium | Corrective retry prompt; `extract_json` with three fallback strategies; Pydantic validation with sensible defaults |
| LLM semaphore causes asyncio deadlock if steps nest calls | Low | Semaphore is acquired/released within `LLMProvider.complete()` only; steps never hold semaphore across `await` boundaries |
| Sentiment rounding edge case (e.g., 33/33/34 split) | Medium | `test_aggregate_distribution_sums_to_100` property test covers all integer splits up to n=100 |
| InsightGenerator prompt exceeds 7B model context window | Medium | Inputs capped: top 5 articles, top 5 events, content truncated to 500 chars; token estimate check before call |

### Exit Criteria

- [ ] Full pipeline with real Ollama (not mocked) completes in < 60s for AAPL with 10 articles.
- [ ] `GET /api/v1/results/{run_id}` returns report with all sections populated.
- [ ] Report `completeness = "minimal"` when Ollama returns 500 for all LLM steps.
- [ ] Sentiment distribution always sums to 100 across 50 randomized article counts (property test).
- [ ] `GET /api/v1/metrics` returns aggregated data after running the metrics job once.
- [ ] TTL cleanup job correctly soft-deletes runs older than 24h and hard-deletes after grace period.
- [ ] All unit and integration tests pass.

---

## 6. Phase 4 — Frontend and Full Integration

**Duration:** 10–13 working days

### Scope

- Zustand store (all three slices: `analysisSlice`, `settingsSlice`, `uiSlice`).
- `useSSEStream` hook (Fetch API-based SSE consumer with reconnect handling).
- `useAnalysis` hook (POST → SSE lifecycle management).
- All 8 report panel components with loading, populated, partial, and error states.
- `ReasoningViewer` component with animated step entries.
- `TickerInput` + `AnalyzeButton` with validation.
- `SettingsModal` with OpenAI key handling.
- `Panel` base component with collapse/expand and ARIA attributes.
- `PriceTrendChart` with Recharts + accessible data table.
- `SentimentPanel` with distribution bar chart.
- `DataSourcesPanel`.
- API Documentation page (`/docs` — static RSC).
- Non-financial-advice `Disclaimer` component (always visible).
- Responsive layout (desktop, tablet, mobile).
- Full accessibility audit against WCAG 2.1 AA.
- Vitest unit tests for all components and hooks.
- Playwright E2E tests for primary analysis flow, invalid ticker, settings modal, keyboard navigation.

### Deliverables

- Complete playground UI at `http://localhost:3000`.
- Entering AAPL and clicking Analyze shows the Reasoning Viewer updating in real time, followed by all panels progressively rendering.
- All panels show correct loading skeleton, then populated state, then handle error state correctly.
- Settings modal accepts an OpenAI key, uses it in the next analysis, never writes it to localStorage.
- API documentation page at `/docs` renders all four endpoint definitions.
- Lighthouse accessibility score ≥ 90 on the playground page.
- All Playwright tests pass.

### Dependencies

- Phase 3 complete (all API endpoints functional and tested).
- API contract stable (no breaking changes expected from backend after Phase 3 exit).

### Complexity

- Medium-High. The progressive rendering pattern (panels appearing as SSE events arrive) requires careful state derivation logic in `analysisSlice`. The `PriceTrendChart` accessibility pattern (visually-hidden data table) is straightforward but must be tested with a screen reader or axe-core. The `useSSEStream` hook's reconnect + replay behavior requires careful browser API handling.

### Engineering Effort Estimate

| Task | Days |
|---|---|
| Zustand store (3 slices + `useAnalysis` + `useSSEStream` hooks) | 2.5 |
| `TickerInput` + `AnalyzeButton` + validation | 1.0 |
| `Panel` base + `PanelSkeleton` + `StatusIndicator` + `ErrorState` | 1.0 |
| `ReasoningViewer` + `StepEntry` with animation | 1.0 |
| `StockOverviewPanel` + price direction component | 1.0 |
| `PriceTrendChart` (Recharts + accessible table) | 1.5 |
| `NewsSummaryPanel` + `ArticleCard` | 1.0 |
| `SentimentPanel` (bar chart + dominant label) | 1.0 |
| `EventsPanel` + `InsightPanel` + `DataSourcesPanel` | 1.5 |
| `SettingsModal` (key handling, masked input, session-only disclosure) | 1.0 |
| API docs page (`/docs` — RSC, static) | 1.0 |
| Responsive layout (grid, mobile breakpoints) | 1.0 |
| Accessibility audit + fixes (axe-core, keyboard nav, ARIA) | 1.5 |
| Vitest unit tests (components + hooks + formatters) | 2.0 |
| Playwright E2E tests | 2.0 |
| **Total** | **20.0 days → 13 focused days** |

*Note: For a two-person team, frontend (Phase 4) can run in parallel with Phase 3 backend AI pipeline work from Week 4 onward, using mock API responses (MSW) until the real backend is ready.*

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| SSE + Next.js App Router `fetch` stream incompatibility | Low | Use Fetch API `ReadableStream` directly (not `EventSource`); well-documented pattern |
| Recharts breaks SSR in Next.js App Router | Medium | Use `next/dynamic` with `ssr: false` for the chart component; tested pattern |
| Panel progressive rendering causes visual flash/reorder | Medium | `ReportGrid` renders all panel slots with `PanelSkeleton` immediately; panels replace skeleton in place as data arrives |
| WCAG 2.1 AA failures discovered late in accessibility audit | Medium | Use `@axe-core/react` in development mode to surface violations at component render time |

### Exit Criteria

- [ ] Full analysis flow works end-to-end in the browser: input → Reasoning Viewer → all 8 panels populated.
- [ ] All panels show correct error state when corresponding step fails (tested with mock backend).
- [ ] OpenAI key is not written to `localStorage` at any point (Playwright test verifies).
- [ ] `window.localStorage` is empty after a full analysis run (no state leaks).
- [ ] `axe-core` reports zero WCAG 2.1 AA violations on the playground page.
- [ ] All Playwright tests pass on Chromium.
- [ ] Vitest unit test coverage ≥ 80% for `hooks/` and `store/`.
- [ ] `/docs` page loads and renders all API endpoint documentation.

---

## 7. Phase 5 — Production Hardening and Launch

**Duration:** 8–10 working days

### Scope

- Production Docker Compose configuration (`docker-compose.prod.yml`).
- Nginx production configuration with TLS, security headers, rate limiting.
- Let's Encrypt certificate provisioning (Certbot).
- GitHub Actions `deploy-production` job (SSH deploy with health check).
- Backup container and cron schedule.
- Backup encryption key rotation setup.
- Grafana alerting rules (pipeline error rate, P95 latency, Ollama unreachable, backup missed).
- Load test run with `locust` (10 and 25 concurrent users).
- Full release checklist execution.
- `CHANGELOG.md` and `README.md` finalized.
- Security review against the checklist in `07_SECURITY_MODEL.md`.
- Non-financial-advice disclaimer final text review.
- Phase 1 PRD feature verification (all 12 MVP features confirmed working).

### Deliverables

- Application live at production URL with HTTPS.
- `/health` endpoint returning 200 in production.
- First nightly backup runs and is verified by the integrity check script.
- Grafana dashboard live with all alert rules configured.
- `locust` load test passes 10-concurrent-user target (P50 < 45s, P95 < 75s, error rate < 1%).
- All 12 PRD Phase 1 features manually verified on the production URL.
- README includes: project description, architecture overview, local setup instructions, API documentation link.

### Dependencies

- Phase 4 complete.
- Production server provisioned (minimum: 2 vCPU, 8GB RAM for Ollama CPU inference; 16GB RAM preferred).
- Domain name and DNS configured.
- GitHub repository secrets configured: `PROD_HOST`, `PROD_USER`, `PROD_SSH_KEY`, `BACKUP_ENCRYPTION_KEY`.

### Complexity

- Medium. Most of Phase 5 is operational — the engineering is done. The main risk is Ollama CPU inference performance on the production server under concurrent load.

### Engineering Effort Estimate

| Task | Days |
|---|---|
| Production Docker Compose + Nginx TLS config | 1.0 |
| Let's Encrypt Certbot setup + renewal cron | 0.5 |
| GitHub Actions `deploy-production` job | 1.0 |
| Backup container + cron schedule + encryption key setup | 1.5 |
| Grafana alerting rules + notification channel | 1.0 |
| Locust load test execution + analysis | 1.0 |
| Security checklist review + any fixes | 1.0 |
| PRD Phase 1 feature verification (manual test matrix) | 1.0 |
| README + CHANGELOG + API docs final pass | 1.0 |
| Deployment to production + first backup verification | 1.0 |
| **Total** | **10.0 days** |

### Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Ollama CPU inference too slow on production hardware | High (if < 8GB RAM / no GPU) | Deploy on a machine with GPU; or use a cloud GPU instance (Fly.io GPU, Modal, Replicate) |
| Let's Encrypt rate limits during certificate provisioning | Low | Use staging LE endpoint for testing; only switch to production endpoint for the real domain |
| Load test reveals Redis connection pool exhaustion | Medium | Increase `max_connections` in `aioredis`; add Redis connection metrics to Grafana |
| `backup.sh` fails on production DB URL format difference | Low | Test backup script in staging environment with production-equivalent credentials before launch |

### Exit Criteria

- [ ] `https://stocklens.example.com` loads the playground page with valid TLS certificate.
- [ ] AAPL analysis completes in < 60s on production hardware.
- [ ] `GET /health` returns `{"status": "healthy"}` with all checks passing.
- [ ] First backup file created, encrypted, and verified by the integrity check script.
- [ ] Grafana dashboard shows live pipeline metrics.
- [ ] `locust` 10-user load test: P50 < 45s, error rate < 1%.
- [ ] All 12 PRD Phase 1 features verified against the manual test matrix below.
- [ ] Zero HIGH/CRITICAL items on the security checklist.

---

## 8. PRD Phase 1 Feature Verification Matrix

| # | Feature | Test Input | Expected Output | Pass |
|---|---|---|---|---|
| 1 | Ticker input + validation | `123` | Inline error: "Ticker may only contain letters and periods" | |
| 2 | Ticker input + validation | `AAPL` | Pipeline triggers; Reasoning Viewer appears | |
| 3 | Market data display | `AAPL` | Stock overview panel shows price, change, volume, market cap, P/E | |
| 4 | Market data — missing fields | Delisted ticker | Missing fields show "N/A" | |
| 5 | Price trend chart | `AAPL` | Line chart renders with 3-month history; trend label visible | |
| 6 | News retrieval | `AAPL` | News Summary Panel shows ≥ 1 article with title, source, date | |
| 7 | News links | Any news article | Link opens in new tab | |
| 8 | Sentiment display | `AAPL` (≥ 3 articles) | Sentiment bar chart shows distribution summing to 100%; dominant label shown | |
| 9 | Sentiment caveat | Ticker with < 3 articles | "Based on limited sources" caveat shown | |
| 10 | AI summaries | `AAPL` | Each article has 1–2 sentence AI summary with topic tags | |
| 11 | AI insights | `AAPL` | AI Insight Panel shows all 6 sections; disclaimer visible | |
| 12 | Agent Reasoning Viewer | `AAPL` | All 9 steps appear in order with status and duration | |
| 13 | Data Sources Panel | `AAPL` | Panel lists data providers used | |
| 14 | Non-financial-advice disclaimer | Any page | Disclaimer visible without scrolling | |
| 15 | Settings modal — OpenAI key | Enter `sk-test-...` | Key saved for session; "Using: OpenAI gpt-4o-mini" in Reasoning Viewer | |
| 16 | Settings modal — key not stored | Enter and save key | `localStorage` empty after analysis | |
| 17 | Rate limit | Submit 11 requests in 60s | 11th returns 429 with `retry_after` | |
| 18 | Error states | Kill Ollama container mid-analysis | AI panels show error state; market data panels still populated | |
| 19 | `GET /api/v1/results/{run_id}` | Valid run_id from a completed run | Returns full JSON report | |
| 20 | `GET /api/v1/results/{run_id}` | Expired/unknown run_id | Returns 404 with `error_code` | |
| 21 | `GET /api/v1/metrics` | Any request | Returns JSON with run counts and latency percentiles | |
| 22 | Pipeline timeout | Inject 200s delay into Ollama mock | "Analysis timed out" notice shown after 90s | |

---

## 9. Post-Launch: Phase 2 Preparation

After Phase 1 launch, the following Phase 2 work items are pre-scoped. They do not begin until Phase 1 is live and stable for at least one week.

| Phase 2 Item | Prerequisite | Estimated Effort |
|---|---|---|
| Event extraction panel (already implemented in backend) — enable in UI | Phase 1 stable | 2 days |
| Multiple timeframe selector on price chart | Phase 1 stable | 2 days |
| `GET /api/v1/news/{ticker}` endpoint (already implemented) — document and expose | Phase 1 stable | 1 day |
| Optional OpenAI key UI (already implemented) — Phase 2 because it requires UX polish | Phase 1 stable | 1 day |
| Second news source (NewsAPI or GNews with free-tier key) | Phase 1 news retrieval stable | 3 days |
| Past analysis results retention UI (show "Load previous analysis" affordance) | Phase 1 stable | 3 days |
| Mobile responsive optimization (< 768px breakpoint polish) | Phase 1 desktop complete | 3 days |
| WAL archiving for PostgreSQL PITR | Production server confirmed stable | 2 days |

---

## 10. Long-Term Evolution Strategy

### Scaling the LLM Layer

**Current state:** Single Ollama instance; semaphore-limited to 3 concurrent inferences.

**Evolution path:**

1. **GPU upgrade:** Move Ollama to a dedicated host with NVIDIA GPU (RTX 3090 / A100). Inference time drops from 3–8s to 0.5–2s per call. Pipeline P50 drops to ~15s.
2. **vLLM migration (Phase 3+):** Replace Ollama with `vllm` for continuous batching. Handles 10+ concurrent inference requests without serialization. API is compatible (OpenAI-compatible endpoint).
3. **Model quality upgrade:** When `mistral:7b-instruct` output quality is insufficient for the event extraction or insight generation tasks, upgrade to `mistral:22b` or a fine-tuned financial-domain model. The `LLMProvider` abstraction makes this a configuration change.

### Scaling the Data Layer

**Current state:** Single PostgreSQL instance; 24h retention; ~500MB max table size.

**Evolution path:**

1. **Managed PostgreSQL (Phase 2):** Move to Supabase, RDS, or Neon for automatic backups, connection pooling (PgBouncer), and read replicas.
2. **Longer retention + analytics (Phase 3+):** Increase run retention to 7 or 30 days. Add a `ticker_analytics` table for aggregated per-ticker statistics. Enable the "Historical trend comparison" feature described in PRD Phase 3.
3. **Vector search (Future):** Embed historical article summaries using a lightweight embedding model. Store embeddings in `pgvector` (PostgreSQL extension). Enable the "Embedding search over historical articles" future enhancement from the PRD.

### Scaling the API Layer

**Current state:** Single FastAPI process; `asyncio`-based concurrency.

**Evolution path:**

1. **Horizontal scaling (Phase 2+):** Run multiple API container replicas behind the Nginx `upstream` block. All shared state is in Redis and PostgreSQL — no per-process state. SSE connections use Redis Pub/Sub, so any replica can serve any stream.
2. **CDN + edge caching (Phase 3+):** Put Cloudflare in front of Nginx for DDoS protection, CDN caching of static assets, and edge-level rate limiting at scale.
3. **Background job queue (Phase 3+):** If pipeline volume exceeds what `asyncio.create_task` can handle (estimated at ~100 concurrent pipelines), introduce `ARQ` (async Redis queue) to distribute pipeline tasks across dedicated worker containers.

### Monetization Path (Future)

The architecture is designed to support a freemium model without requiring structural changes:

- **Free tier (current):** Ollama local inference, limited to 10 requests/minute per IP, 24h result retention.
- **API tier (Phase 3+):** API key-gated access (replace per-IP rate limiting with per-key rate limiting for the API). Higher rate limits, longer retention window, guaranteed SLAs.
- **Premium tier (Future):** OpenAI-powered analysis included (no user-provided key required). Requires adding server-side OpenAI key management, billing integration, and a minimal account model. The `LLMProvider` abstraction makes this a new dependency injection path, not an architectural change.

### Technical Debt Inventory

Items to address in Phase 2–3 before they compound:

| Item | Current State | Target State | Phase |
|---|---|---|---|
| yfinance unofficial API dependency | `MarketDataProvider` interface isolates it | Add Alpha Vantage adapter as primary; keep yfinance as fallback | 2 |
| `asyncio.create_task` pipeline (no persistence across restarts) | Acceptable for MVP | Migrate to ARQ if pipeline volume exceeds ~50 concurrent runs | 3 |
| SimHash O(n²) dedup (n capped at 20) | Acceptable for n≤20 | LSH-based approximate nearest neighbor for n>50 | 3 |
| `report_data` jsonb versioning (manual `schema_version` check) | Works for MVP | Add Pydantic discriminated union for version dispatch | 2 |
| No dark mode | CSS vars defined but not toggled | Add `prefers-color-scheme` toggle and user preference persistence | 2 |
| Prometheus `/metrics` endpoint exposed on same app port | Blocked by Nginx; acceptable | Move to dedicated internal port (not proxied by Nginx at all) | 2 |
| SSE reconnect redelivers all events (full replay) | Acceptable; harmless idempotent re-render | Add client-side last-received event ID tracking; `LRANGE` from last position | 3 |
