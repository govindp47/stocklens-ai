# 02_TECH_DECISIONS.md — StockLens AI

---

## 1. Programming Language — Backend

### Selected: Python 3.11+

**Alternatives Considered:**

- Node.js (TypeScript)
- Go

**Trade-offs:**

| Factor | Python | Node.js | Go |
|---|---|---|---|
| LLM ecosystem | Best-in-class (`langchain`, `openai`, `ollama` libs) | Good but secondary | Minimal |
| Async I/O | `asyncio` — mature, fits I/O-bound pipeline | Native event loop | Goroutines — superior for concurrency |
| yfinance / financial data libs | Native Python (`yfinance`, `pandas`) | No equivalent | No equivalent |
| Speed of implementation | Fastest for this domain | Fast | Slowest |
| Runtime performance | Adequate for I/O-bound + LLM-bound workloads | Adequate | Best |

**Justification:** The pipeline is overwhelmingly I/O-bound and LLM-bound. Python's ecosystem dominance in financial data, NLP, and LLM integration is decisive. `asyncio` handles the concurrent pipeline runs adequately. Python 3.11 specifically for its 10–60% CPython performance improvements over 3.10 and its improved `asyncio` task performance.

**Explicit Assumption:** LLM inference latency (2–15s per call) dwarfs any difference between Python, Node.js, and Go for the request-handling portions of the system.

---

## 2. Programming Language — Frontend

### Selected: TypeScript 5.x (strict mode)

**Alternatives Considered:**

- JavaScript (untyped)
- Elm

**Trade-offs:**

| Factor | TypeScript | JavaScript | Elm |
|---|---|---|---|
| Type safety | Full | None | Full (stronger than TS) |
| Ecosystem | Full React/Next.js support | Same | Limited |
| SSE typing | Full with generics | Runtime only | Requires FFI |
| Learning overhead | Low for JS developers | None | High |

**Justification:** TypeScript's strict mode catches the class of bugs that are most common in progressive-rendering UIs (accessing `undefined` fields from partially-loaded API responses, mismatched event shapes). The investment is minimal given the team's likely JS background. Elm is overkill for this scope and has a narrow hiring pool.

---

## 3. Backend Framework

### Selected: FastAPI 0.110+

**Alternatives Considered:**

- Django REST Framework
- Flask + extensions
- Litestar

**Trade-offs:**

| Factor | FastAPI | Django REST | Flask |
|---|---|---|---|
| Native `async` support | First-class | Bolted on (ASGI adapter) | Requires extension |
| SSE / streaming responses | `StreamingResponse` built-in | Awkward | Manual |
| Pydantic v2 integration | Native | Third-party | Third-party |
| Startup time | Fast | Slow (ORM, settings machinery) | Fast |
| OpenAPI generation | Automatic | DRF's own schema (less ergonomic) | Manual/extension |
| Background tasks | `BackgroundTasks` / `asyncio.create_task` | Requires Celery for async | Manual |

**Justification:** FastAPI is the only framework in this list where async background tasks, SSE streaming, Pydantic validation, and OpenAPI generation are first-class features with no friction. The streaming pipeline delivery pattern is a core architectural requirement, not a secondary feature.

**Specific FastAPI features used:**

- `StreamingResponse` with `media_type="text/event-stream"` for SSE.
- `BackgroundTasks` for lightweight in-process task launch.
- `Depends()` for injecting `PipelineOrchestrator`, `RateLimiter`, and `LLMProvider` per-request.
- Lifespan context manager for connection pool initialization and cleanup.

---

## 4. Frontend Framework

### Selected: Next.js 14 (App Router) + React 18

**Alternatives Considered:**

- Vite + React SPA (no SSR)
- SvelteKit
- Remix

**Trade-offs:**

| Factor | Next.js 14 | Vite + React | SvelteKit | Remix |
|---|---|---|---|---|
| SSR for SEO | Yes (App Router RSC) | No | Yes | Yes |
| Static export for API docs page | Yes | Yes | Yes | Limited |
| SSE consumption | Standard `fetch` + `ReadableStream` | Same | Same | Same |
| Bundle optimization | Excellent (RSC, code splitting) | Good | Excellent | Good |
| Ecosystem/hiring | Largest | Large | Growing | Medium |
| Streaming UI patterns | Built-in `Suspense` + RSC | Manual | Built-in | Built-in |

**Justification:** Next.js 14 App Router's React Server Components allow the static sections of the page (header, API docs page, settings modal structure) to render with zero client JS. The interactive panel grid is a Client Component. The combination gives both SEO-friendly rendering for the playground's landing state and efficient client-side streaming for the analysis in-progress state. Vite + React was the closest alternative, but lacks the server-side rendering needed for the API docs page and the `<head>` management for the disclaimer metadata.

**Key technical choices within Next.js:**

- App Router (not Pages Router) for React Server Component support.
- Server Actions are NOT used for the analysis trigger — a direct `fetch` to the FastAPI backend is used instead, to keep the backend independently deployable.
- `next/dynamic` with `ssr: false` for the price chart component (Recharts does not support SSR).

---

## 5. Architecture Pattern

### Selected: Layered Clean Architecture with Pipeline Pattern

**Alternatives Considered:**

- Hexagonal Architecture (Ports and Adapters)
- Service Layer (flat)
- Event-Driven (full CQRS)

**Trade-offs:**

| Factor | Layered Clean | Hexagonal | Flat Service | CQRS |
|---|---|---|---|---|
| Dependency isolation | High | High | Low | High |
| Complexity | Medium | High | Low | Very High |
| Testability | High | High | Medium | High |
| Fit for sequential pipeline | Natural | Natural | Natural | Overcomplicated |
| Team ramp-up | Medium | High | Low | Very High |

**Justification:** The pipeline pattern (sequential steps with shared context) is a natural fit for the 9-step analysis workflow. Clean architecture layers ensure that infrastructure concerns (yfinance, Ollama HTTP clients) are fully swappable behind interfaces — critical for testing (mock providers) and for the OpenAI fallback feature. Full CQRS would add command/event bus infrastructure complexity that provides no benefit for this scale.

---

## 6. Dependency Injection

### Selected: FastAPI `Depends()` + Manual Constructor Injection

**Alternatives Considered:**

- `dependency-injector` (Python DI container)
- `punq`
- Manual factory functions

**Trade-offs:**

| Factor | FastAPI Depends | dependency-injector | Manual factories |
|---|---|---|---|
| Learning curve | Low (FastAPI-native) | Medium | None |
| Scoped injection (request vs. app) | Built-in | Configurable | Manual |
| Integration with async | First-class | Good | Manual |
| Testing overrides | `app.dependency_overrides` | Container substitution | Direct |

**Justification:** `FastAPI Depends()` provides scoped injection (app-level singletons for connection pools and orchestrators; request-level for extracting the `X-OpenAI-Key` header and constructing the `LLMProvider`). It requires zero additional libraries and is idiomatic FastAPI. The `app.dependency_overrides` mechanism is used in tests to inject mock providers without modifying production code.

**Wiring example:**

```python
# App-scoped singleton
async def get_orchestrator() -> PipelineOrchestrator:
    return app.state.orchestrator  # initialized in lifespan

# Request-scoped
async def get_llm_provider(
    x_openai_key: Optional[str] = Header(default=None, alias="X-OpenAI-Key"),
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator)
) -> LLMProvider:
    if x_openai_key:
        return OpenAIProvider(api_key=x_openai_key, model="gpt-4o-mini")
    return OllamaProvider(base_url=settings.ollama_url, model=settings.default_model)
```

---

## 7. Database Technology

### Selected: PostgreSQL 15

**Alternatives Considered:**

- SQLite
- MongoDB
- DynamoDB

**Trade-offs:**

| Factor | PostgreSQL | SQLite | MongoDB | DynamoDB |
|---|---|---|---|---|
| ACID compliance | Full | Full | Document-level | Limited |
| JSON column support | `jsonb` — indexed, queryable | JSON as text | Native | Limited |
| Async driver (`asyncpg`) | Yes — best-in-class async | `aiosqlite` (limited) | `motor` | `aioboto3` |
| Operational simplicity | Needs a process | Zero-config | Needs a process | Fully managed |
| Production readiness | Battle-hardened | Single-file; not for concurrent writes | Good | AWS-specific |
| Migration tooling | `alembic` — mature | `alembic` works | Manual | Limited |

**Justification:** PostgreSQL's `jsonb` type is ideal for storing assembled report documents (variable-schema JSON) with the ability to query specific fields (e.g., `report_data->>'ticker'`) without deserializing the entire blob. `asyncpg` is the fastest async PostgreSQL driver for Python — measurably faster than `psycopg3` async for high-throughput scenarios. SQLite was considered for MVP simplicity but is not suitable for concurrent writes from multiple asyncio tasks in the same process.

**Note:** For MVP, PostgreSQL runs as a Docker container. The schema is intentionally minimal — the `analysis_runs` table stores the full report as `jsonb`. No ORM is used; raw `asyncpg` SQL is used directly for full control over query plans.

---

## 8. Serialization Strategy

### Selected: Pydantic v2 (data validation + serialization)

**Alternatives Considered:**

- `attrs` + `cattrs`
- `marshmallow`
- `dataclasses` (stdlib)

**Trade-offs:**

| Factor | Pydantic v2 | attrs/cattrs | marshmallow | dataclasses |
|---|---|---|---|---|
| FastAPI integration | Native (no extra code) | Manual | Manual | Partial |
| Validation | Comprehensive, type-based | Via validators | Via schema | None |
| Performance (v2) | Rust core — very fast | Fast | Slower | N/A |
| JSON schema generation | Automatic | Manual | Automatic | None |
| Nested model support | First-class | Good | Good | Basic |

**Justification:** Pydantic v2 is the only reasonable choice given FastAPI's native integration. Its Rust-based core provides validation performance that eliminates serialization as a bottleneck in the pipeline. `model_validate_json()` is used for parsing LLM JSON responses (with error handling for malformed output). `model_dump(mode="json")` is used for SSE event serialization.

**Pydantic models for key domain objects:**

- `AnalyzeRequest` — input validation
- `StepEvent` — SSE event shape
- `PipelineEvent` — terminal SSE event shape
- `AnalysisReport` — full assembled report (nested Pydantic models per section)
- `ArticleSummary`, `SentimentResult`, `ExtractedEvent`, `InsightSections` — step output models

---

## 9. Background Processing

### Selected: `asyncio.create_task()` (in-process)

**Alternatives Considered:**

- Celery + Redis broker
- ARQ (async Redis Queue)
- FastAPI `BackgroundTasks`

**Trade-offs:**

| Factor | asyncio.create_task | Celery | ARQ | FastAPI BackgroundTasks |
|---|---|---|---|---|
| Operational overhead | None | High (worker process) | Medium | None |
| Task persistence across restarts | None | Yes (Redis/RabbitMQ) | Yes (Redis) | None |
| Monitoring | asyncio task inspection | Flower + broker UI | Custom | None |
| Scalability | Single process | Multi-worker | Multi-worker | Single process |
| Fit for < 90s tasks | Ideal | Overcomplicated | Good | Adequate |
| Task cancellation | `task.cancel()` | `task.revoke()` | `job.abort()` | Not supported |

**Justification:** The pipeline is guaranteed to complete (or timeout) within 90 seconds. There is no requirement for task persistence across server restarts (if the server restarts, the user resubmits). Celery adds a worker process, broker configuration, and operational complexity that is entirely disproportionate for this use case. `asyncio.create_task()` with a watchdog timeout task is the simplest correct solution.

**Justification for not using FastAPI `BackgroundTasks`:** `BackgroundTasks` runs after the response is sent and does not support task cancellation or independent error tracking. `asyncio.create_task()` allows the pipeline task to be referenced (for cancellation by the watchdog) and its exceptions to be caught via a done-callback.

---

## 10. Messaging / Event System

### Selected: Redis Pub/Sub + Redis List (append-only replay buffer)

**Alternatives Considered:**

- In-process `asyncio.Queue`
- Kafka
- RabbitMQ

**Trade-offs:**

| Factor | Redis Pub/Sub + List | asyncio.Queue | Kafka | RabbitMQ |
|---|---|---|---|---|
| Cross-process delivery | Yes | No | Yes | Yes |
| Message replay for reconnects | Via Redis List | No | Yes (offsets) | No (unless persisted) |
| Operational overhead | Low (Redis already in stack) | None | Very High | High |
| Latency | Sub-millisecond | Sub-microsecond | Milliseconds | Milliseconds |
| Persistence | TTL-based (sufficient) | None | Full (days) | Configurable |
| Scale | Single Redis node sufficient | Single process only | Cluster required for scale | Medium |

**Justification:** Redis Pub/Sub with a parallel List for event replay is the correct solution for this scale. The List (appended on every step event) enables the SSE router to replay all events that occurred before the client connected — critical for the case where the browser takes a few seconds to establish the SSE connection after receiving the `run_id`. `asyncio.Queue` was rejected because SSE connections come in on different asyncio tasks than the pipeline task; sharing a `Queue` between them requires passing it through a registry, which is architecturally equivalent to Redis but without the replay capability.

**Event schema:**

```json
{
  "event_type": "step_event",
  "run_id": "uuid",
  "step_name": "MarketDataCollector",
  "step_index": 2,
  "status": "complete | failed | in_progress",
  "timestamp_ms": 1709000000000,
  "data": { ... },
  "reason": "string | null"
}
```

---

## 11. Logging Framework

### Selected: `structlog` 24.x

**Alternatives Considered:**

- Python stdlib `logging`
- `loguru`

**Trade-offs:**

| Factor | structlog | stdlib logging | loguru |
|---|---|---|---|
| Structured JSON output | First-class | Via formatter | Via formatter |
| Async-safe | Yes | Yes | Yes |
| Context binding (run_id, ticker) | `structlog.contextvars` | Manual | `bind()` (limited context propagation) |
| Integration with stdlib | Via `structlog.stdlib` | N/A | Via `logging.Handler` |
| Performance | Very fast | Fast | Fast |

**Justification:** `structlog.contextvars.bind_contextvars(run_id=run_id, ticker=ticker)` at the start of each pipeline task automatically attaches context to every log record emitted anywhere in the call stack during that task. This eliminates the need to thread context objects through every function signature. The JSON output format integrates directly with Loki log aggregation.

---

## 12. Monitoring Strategy

### Selected: Prometheus + Grafana + Loki

**Alternatives Considered:**

- Datadog
- New Relic
- OpenTelemetry → Jaeger (traces only)

**Trade-offs:**

| Factor | Prometheus/Grafana/Loki | Datadog | New Relic |
|---|---|---|---|
| Cost | Free (self-hosted) | High SaaS cost | High SaaS cost |
| Fit for portfolio project | Ideal | Overcomplicated | Overcomplicated |
| Custom metrics | First-class | First-class | First-class |
| Log aggregation | Loki (lightweight) | Yes | Yes |
| Distributed tracing | Jaeger (via OTLP) | Yes | Yes |
| Operational overhead | Low (Docker Compose) | None (SaaS) | None (SaaS) |

**Justification:** Prometheus + Grafana is the industry-standard open-source stack and costs nothing. For a portfolio project with demo-scale traffic, self-hosted monitoring in Docker Compose is the correct operational choice. Datadog and New Relic are appropriate for funded production systems; they are disproportionate here.

**Stack composition:**

- `prometheus_fastapi_instrumentator` for automatic HTTP metrics.
- `prometheus_client` for custom pipeline metrics.
- Grafana for dashboards.
- Loki + Promtail (or Alloy) for log ingestion from container stdout.
- Jaeger (OTLP) for distributed traces in development.

---

## 13. CI/CD Tools

### Selected: GitHub Actions

**Alternatives Considered:**

- GitLab CI
- CircleCI
- Jenkins

**Justification:** GitHub Actions is the default choice for a GitHub-hosted repository. It requires zero additional infrastructure, has native Docker build support (`docker/build-push-action`), supports self-hosted runners if GPU-based Ollama testing is needed, and integrates natively with GitHub Packages for Docker image publishing. All alternatives add operational overhead without meaningful benefit at this scale.

**Pipeline stages:**

1. `lint-and-type-check`: `ruff`, `mypy` (backend); `eslint`, `tsc --noEmit` (frontend).
2. `unit-tests`: `pytest` with mocked providers.
3. `integration-tests`: `pytest` against a `docker compose` test environment (PostgreSQL + Redis + mock Ollama).
4. `build`: `docker buildx build` for backend and frontend images.
5. `push`: Push to GitHub Container Registry on `main` branch merge.
6. `deploy`: SSH into the target server and run `docker compose pull && docker compose up -d` (for MVP). Alternatively: trigger a Fly.io or Render deployment via their CLI.

---

## 14. Code Quality Enforcement

### Selected: `ruff` (lint + format) + `mypy` (type checking) — Backend; `eslint` + Prettier + `tsc` — Frontend

**Backend:**

| Tool | Role | Alternative |
|---|---|---|
| `ruff` | Linting (replaces `flake8`, `isort`, `pyupgrade`) + formatting (replaces `black`) | `black` + `flake8` (slower, multiple tools) |
| `mypy` (strict mode) | Static type checking | `pyright`, `pylance` |
| `pytest` + `pytest-asyncio` | Testing | `unittest` (inferior for async) |
| `pytest-cov` | Coverage reporting | N/A |

**Frontend:**

| Tool | Role |
|---|---|
| `eslint` with `@typescript-eslint` | Linting |
| Prettier | Formatting |
| `tsc --noEmit` | Type checking |
| Vitest | Unit testing |
| Playwright | E2E testing |

**Justification for `ruff`:** `ruff` replaces `black`, `flake8`, `isort`, `pyupgrade`, and `pydocstyle` with a single Rust-based tool that runs in milliseconds. For a project of this size, it eliminates the friction of maintaining multiple linting tool configurations. `mypy` in strict mode catches the category of type errors (missing `Optional` checks, incorrect return types from LLM output parsers) that are most likely to surface as runtime crashes in the pipeline.

**Pre-commit hooks:** `pre-commit` is configured with `ruff`, `mypy`, and `prettier` hooks. This enforces quality locally before CI runs, reducing unnecessary CI cycle time.

---

## 15. Financial Data Provider

### Selected: `yfinance` (Yahoo Finance unofficial Python wrapper)

**Alternatives Considered:**

- Alpha Vantage (free tier, API key required)
- Polygon.io (free tier, API key required)
- IEX Cloud (free tier, API key required)

**Trade-offs:**

| Factor | yfinance | Alpha Vantage | Polygon.io |
|---|---|---|---|
| API key required | No | Yes | Yes |
| Rate limits | Informal / unofficial | 5 req/min (free) | 5 req/min (free) |
| Data completeness | Good (price, ratios, history) | Good | Excellent |
| Stability / reliability | Unofficial — can break on Yahoo changes | Stable | Stable |
| Cost | Free | Free tier | Free tier |

**Justification:** The PRD explicitly states the goal of operating "without requiring user accounts, payments, or proprietary API keys by default." `yfinance` is the only option that satisfies this constraint without any registration. The risk of `yfinance` breaking (it scrapes Yahoo Finance's internal API) is mitigated by the graceful degradation architecture: if `yfinance` returns no data, the market data step fails non-critically and the pipeline continues. An adapter interface (`MarketDataProvider`) allows swapping `yfinance` for an alternative without touching the pipeline logic.

---

## 16. News Data Provider

### Selected: RSS Feeds via `feedparser` (Phase 1); extensible to `NewsAPI` / `GNews` in Phase 2

**Alternatives Considered:**

- NewsAPI.org (free tier: 100 req/day, key required)
- GNews API (free tier, key required)
- Direct web scraping

**Trade-offs:**

| Factor | RSS (feedparser) | NewsAPI | GNews |
|---|---|---|---|
| API key required | No | Yes | Yes |
| Rate limits | None (RSS is public) | 100/day free | 100/day free |
| Article volume | Medium (varies by feed) | High | Medium |
| Content quality | Good (major financial sources) | High | Medium |
| Extensibility | Manual feed configuration | Easy | Easy |

**Financial RSS sources for Phase 1:**

- `https://finance.yahoo.com/rss/headline?s={TICKER}` — ticker-specific Yahoo Finance RSS.
- `https://feeds.finance.yahoo.com/rss/2.0/headline?s={TICKER}&region=US&lang=en-US` — alternative format.
- `https://www.marketwatch.com/rss/topstories` — general financial news (filtered by ticker mention post-retrieval).

**Justification:** RSS feeds require no API keys, have no official rate limits, and cover major financial news sources adequately for MVP. The `NewsProvider` interface abstracts the RSS-specific implementation; adding a `NewsAPIProvider` in Phase 2 is a new infrastructure adapter only, requiring no changes to the pipeline steps.

---

## 17. LLM Inference

### Selected: Ollama (local) with OpenAI fallback

**Model Selection:**

| Model | Size | Speed | Quality |
|---|---|---|---|
| `mistral:7b-instruct` | 4.1GB quantized | Fast (CPU-feasible) | Good for structured tasks |
| `llama3:8b-instruct` | 4.7GB quantized | Fast | Slightly better instruction following |
| `gpt-4o-mini` | N/A (API) | Fast | Very high |
| `gpt-4o` | N/A (API) | Medium | Highest |

**Default model:** `mistral:7b-instruct` — smallest acceptable quality/speed balance; fits in 8GB RAM without GPU.

**Justification for Ollama:** Runs locally, requires no API key, no billing. All AI analysis steps work out of the box for demo purposes. The `LLMProvider` abstraction means OpenAI is a drop-in replacement when a user supplies a key.

**Prompt design strategy:** All prompts instruct the model to respond exclusively in JSON (`"Respond only with valid JSON, no other text"`). Responses are validated against Pydantic models. If JSON parsing fails, the step retries once with a more constrained prompt suffix (`"Your previous response was not valid JSON. Respond ONLY with the JSON object, starting with { and ending with }"`). On second failure, the step fails non-critically.

---

## 18. HTTP Client

### Selected: `httpx` (async) for all external HTTP calls

**Alternatives Considered:**

- `aiohttp`
- `requests` (sync, rejected)

**Justification:** `httpx` has a unified sync/async API, first-class HTTP/2 support, and timeout configuration at both the client and per-request level. `aiohttp` is functionally equivalent but has a less ergonomic API for setting per-request timeouts and for mocking in tests (`respx` provides `httpx`-compatible request mocking). `requests` is a hard reject — blocking synchronous I/O in an async pipeline would block the entire event loop.

---

## 19. Price Chart Library

### Selected: Recharts (React)

**Alternatives Considered:**

- TradingView Lightweight Charts
- Chart.js + react-chartjs-2
- D3.js (direct)
- Highcharts

**Trade-offs:**

| Factor | Recharts | TradingView | Chart.js | D3.js |
|---|---|---|---|---|
| React-native API | Yes | No (imperative) | Via wrapper | No |
| Bundle size | Medium (60KB gz) | Small (45KB gz) | Medium | Large |
| License | MIT | MIT | MIT | BSD |
| Customization | High | Medium | High | Unlimited |
| Accessibility | Via ARIA props | Limited | Via plugins | Manual |
| SVG output (accessible) | Yes | Canvas | Canvas | SVG |

**Justification:** Recharts renders to SVG, making the chart accessible (screen readers can traverse SVG elements; a data table alternative can be rendered alongside). Canvas-based libraries (Chart.js, TradingView) require more work to satisfy the WCAG 2.1 AA accessibility requirement that chart data must be accessible via a text alternative. Recharts' React-component API integrates naturally with React state for the timeframe toggle feature. D3.js is rejected on implementation complexity grounds for this use case.

---

## 20. CSS / Styling

### Selected: Tailwind CSS 3.x + shadcn/ui components

**Alternatives Considered:**

- CSS Modules
- Styled-components
- Chakra UI
- MUI

**Trade-offs:**

| Factor | Tailwind + shadcn | CSS Modules | Styled-components | Chakra/MUI |
|---|---|---|---|---|
| Design system coherence | High (design tokens via CSS vars) | Manual | Manual | Very High |
| Bundle size | Small (PurgeCSS) | Small | Medium | Large |
| Dark mode | `dark:` variant | Manual | ThemeProvider | Built-in |
| Accessibility | Via shadcn's Radix primitives | Manual | Manual | Good |
| Customization speed | Very fast | Slow | Medium | Medium |

**Justification:** `shadcn/ui` components are built on Radix UI primitives, which provide WCAG-compliant keyboard navigation and ARIA attributes for all interactive components (modals, toggles, buttons) out of the box. This directly satisfies the WCAG 2.1 AA accessibility requirement without manual ARIA implementation. Tailwind's utility classes enable rapid layout work. Unlike Chakra or MUI, `shadcn/ui` components are copied into the project (not imported from a package), giving full control over component internals.

---

## 21. State Management (Frontend)

### Selected: Zustand + React `useState` for local component state

**Alternatives Considered:**

- Redux Toolkit
- Jotai
- Recoil
- React Context + useReducer

**Trade-offs:**

| Factor | Zustand | Redux Toolkit | Jotai | Context+Reducer |
|---|---|---|---|---|
| Boilerplate | Very low | Medium | Low | Medium |
| Async action handling | Manual (plain functions) | `createAsyncThunk` | Via atoms | Manual |
| DevTools | Yes (Redux DevTools compat.) | Yes | Yes | Basic |
| SSE event handling | Store action from event handler | Dispatch action | Set atom | Dispatch |
| Bundle size | ~1KB | ~12KB | ~3KB | 0KB |

**Justification:** The application state is primarily the pipeline's `run_id`, the ordered list of `StepEvent` objects, and the derived panel data (extracted from step events). This is a linear accumulation of events, not a complex nested state tree. Zustand's simple `set(state => ...)` API is perfectly suited for appending to an array of step events as they arrive from the SSE stream. Redux Toolkit would add significant boilerplate for no architectural benefit at this complexity level.

**Store slices:**

- `analysisSlice`: `runId`, `status`, `stepEvents[]`, `ticker`
- `settingsSlice`: `openAiKey` (in-memory only, never persisted), `modelActive`
- `uiSlice`: `panelExpansionState`, `activeTimeframe`

---

## 22. Containerization

### Selected: Docker + Docker Compose

**Justification:** Standard containerization for all services (FastAPI, Next.js, PostgreSQL, Redis, Ollama, Prometheus, Grafana, Loki). Docker Compose provides single-command local development startup. Docker images are built in CI and pushed to GitHub Container Registry. Production deployment uses `docker compose pull && docker compose up -d` on the target server. No Kubernetes is required for MVP scale.

**Services in `docker-compose.yml`:**

```
services:
  api          # FastAPI + Uvicorn
  frontend     # Next.js
  db           # PostgreSQL 15
  redis        # Redis 7
  ollama       # Ollama with model volume
  nginx        # Reverse proxy + SSL
  prometheus   # Metrics scrape
  grafana      # Dashboards
  loki         # Log aggregation
  promtail     # Log shipping (reads from Docker socket)
```

**Ollama model volume:** The Ollama container mounts a named Docker volume for model storage. On first startup, a `docker compose run ollama pull mistral:7b-instruct` step in the setup script pre-loads the model. This avoids re-downloading on container restarts.
