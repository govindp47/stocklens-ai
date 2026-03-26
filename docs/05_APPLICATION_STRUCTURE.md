# 05_APPLICATION_STRUCTURE.md — StockLens AI

---

## 1. Repository Layout

The project is structured as a monorepo with two deployable applications — the FastAPI backend and the Next.js frontend — sharing no runtime code but colocated for coordinated versioning and CI.

```
stocklens-ai/
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── deploy.yml
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── dependencies.py        ← FastAPI Depends() providers
│   │   │   ├── routers/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── analyze.py         ← POST /api/v1/analyze
│   │   │   │   ├── stream.py          ← GET  /api/v1/analyze/stream/{run_id}
│   │   │   │   ├── results.py         ← GET  /api/v1/results/{run_id}
│   │   │   │   ├── news.py            ← GET  /api/v1/news/{ticker}
│   │   │   │   └── metrics.py         ← GET  /api/v1/metrics
│   │   │   └── models/
│   │   │       ├── __init__.py
│   │   │       ├── requests.py        ← AnalyzeRequest, NewsRequest
│   │   │       └── responses.py       ← AnalyzeResponse, ResultsResponse, MetricsResponse
│   │   ├── pipeline/
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py        ← PipelineOrchestrator
│   │   │   ├── context.py             ← PipelineContext, PipelineOutputs
│   │   │   └── steps/
│   │   │       ├── __init__.py
│   │   │       ├── base.py            ← PipelineStep Protocol, StepResult
│   │   │       ├── ticker_validator.py
│   │   │       ├── market_data_collector.py
│   │   │       ├── news_retriever.py
│   │   │       ├── news_deduplicator.py
│   │   │       ├── article_summarizer.py
│   │   │       ├── sentiment_classifier.py
│   │   │       ├── event_extractor.py
│   │   │       ├── insight_generator.py
│   │   │       └── report_assembler.py
│   │   ├── domain/
│   │   │   ├── __init__.py
│   │   │   ├── models/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── report.py          ← AnalysisReport, all section models
│   │   │   │   ├── market.py          ← MarketData, PriceHistory, CompanyInfo
│   │   │   │   ├── news.py            ← RawArticle, ArticleSummary, NewsCollection
│   │   │   │   ├── sentiment.py       ← SentimentResult, SentimentDistribution
│   │   │   │   ├── events.py          ← ExtractedEvent
│   │   │   │   └── insights.py        ← InsightSections
│   │   │   └── exceptions.py          ← ExternalProviderError, LLMParseError, etc.
│   │   ├── infrastructure/
│   │   │   ├── __init__.py
│   │   │   ├── providers/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── market_data.py     ← yfinance adapter
│   │   │   │   ├── news_feed.py       ← RSS/feedparser adapter
│   │   │   │   ├── llm_ollama.py      ← OllamaProvider
│   │   │   │   └── llm_openai.py      ← OpenAIProvider
│   │   │   ├── repositories/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── report_repository.py
│   │   │   │   ├── metrics_repository.py
│   │   │   │   └── ticker_cache_repository.py
│   │   │   ├── event_bus.py           ← Redis Pub/Sub + List publisher
│   │   │   ├── rate_limiter.py        ← Redis sliding-window limiter
│   │   │   └── cache.py               ← Redis cache get/set helpers
│   │   ├── prompts/
│   │   │   ├── summarize.j2
│   │   │   ├── sentiment.j2
│   │   │   ├── events.j2
│   │   │   └── insights.j2
│   │   ├── jobs/
│   │   │   ├── __init__.py
│   │   │   ├── cleanup.py             ← TTL cleanup job
│   │   │   └── metrics_aggregator.py  ← hourly metrics job
│   │   ├── config.py                  ← Pydantic Settings
│   │   ├── lifespan.py                ← FastAPI lifespan: startup/shutdown hooks
│   │   └── main.py                    ← FastAPI app factory
│   ├── db/
│   │   ├── alembic.ini
│   │   ├── env.py
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── pipeline/
│   │   │   │   ├── test_orchestrator.py
│   │   │   │   └── steps/
│   │   │   │       ├── test_news_deduplicator.py
│   │   │   │       ├── test_sentiment_classifier.py
│   │   │   │       └── ...
│   │   │   └── domain/
│   │   │       ├── test_report_models.py
│   │   │       └── test_sentiment_distribution.py
│   │   ├── integration/
│   │   │   ├── test_analyze_endpoint.py
│   │   │   ├── test_stream_endpoint.py
│   │   │   ├── test_results_endpoint.py
│   │   │   └── test_pipeline_full.py
│   │   └── conftest.py
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── app/
│   │   ├── layout.tsx                 ← Root layout: fonts, metadata, disclaimer
│   │   ├── page.tsx                   ← Playground page (Server Component shell)
│   │   ├── docs/
│   │   │   └── page.tsx               ← API Documentation page (static RSC)
│   │   └── globals.css
│   ├── components/
│   │   ├── playground/
│   │   │   ├── TickerInput.tsx
│   │   │   ├── AnalyzeButton.tsx
│   │   │   ├── ReasoningViewer.tsx
│   │   │   └── ReportGrid.tsx
│   │   ├── panels/
│   │   │   ├── StockOverviewPanel.tsx
│   │   │   ├── PriceTrendChart.tsx
│   │   │   ├── NewsSummaryPanel.tsx
│   │   │   ├── SentimentPanel.tsx
│   │   │   ├── EventsPanel.tsx
│   │   │   ├── InsightPanel.tsx
│   │   │   └── DataSourcesPanel.tsx
│   │   ├── ui/
│   │   │   ├── Panel.tsx              ← Base collapsible panel shell
│   │   │   ├── PanelSkeleton.tsx      ← Loading skeleton
│   │   │   ├── SentimentBadge.tsx
│   │   │   ├── StatusIndicator.tsx
│   │   │   ├── Disclaimer.tsx
│   │   │   └── ErrorBanner.tsx
│   │   ├── settings/
│   │   │   └── SettingsModal.tsx
│   │   └── docs/
│   │       ├── EndpointBlock.tsx
│   │       └── CodeBlock.tsx
│   ├── hooks/
│   │   ├── useAnalysis.ts             ← orchestrates POST + SSE lifecycle
│   │   ├── useSSEStream.ts            ← SSE connection management
│   │   └── usePanelExpansion.ts
│   ├── store/
│   │   ├── index.ts                   ← Zustand store root
│   │   ├── analysisSlice.ts
│   │   ├── settingsSlice.ts
│   │   └── uiSlice.ts
│   ├── lib/
│   │   ├── api.ts                     ← typed fetch wrappers for backend API
│   │   ├── sse.ts                     ← SSE consumer utility
│   │   ├── formatters.ts              ← price/date/percentage formatters
│   │   ├── validators.ts              ← client-side ticker format validator
│   │   └── constants.ts
│   ├── types/
│   │   ├── api.ts                     ← TypeScript types mirroring Pydantic models
│   │   ├── pipeline.ts                ← StepEvent, PipelineEvent types
│   │   └── report.ts                  ← AnalysisReport, all section types
│   ├── public/
│   │   └── favicon.ico
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── .env.local.example
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.test.yml
│   ├── nginx/
│   │   ├── nginx.conf
│   │   └── ssl/                       ← (gitignored; certs mounted at deploy time)
│   └── monitoring/
│       ├── prometheus.yml
│       ├── grafana/
│       │   └── dashboards/
│       │       └── stocklens.json
│       └── loki/
│           └── loki-config.yml
└── README.md
```

---

## 2. Backend Module Structure — Detailed

### 2.1 `app/main.py` — Application Factory

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.lifespan import lifespan
from app.api.routers import analyze, stream, results, news, metrics
from prometheus_fastapi_instrumentator import Instrumentator

def create_app() -> FastAPI:
    app = FastAPI(
        title="StockLens AI",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json"
    )

    # Routers
    app.include_router(analyze.router,  prefix="/api/v1")
    app.include_router(stream.router,   prefix="/api/v1")
    app.include_router(results.router,  prefix="/api/v1")
    app.include_router(news.router,     prefix="/api/v1")
    app.include_router(metrics.router,  prefix="/api/v1")

    # Prometheus instrumentation
    Instrumentator().instrument(app).expose(app, endpoint="/metrics")

    return app

app = create_app()
```

### 2.2 `app/lifespan.py` — Startup / Shutdown

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────
    settings = get_settings()

    # Database pool
    app.state.db_pool = await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=2,
        max_size=10,
        command_timeout=10
    )

    # Redis pool
    app.state.redis = await aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20
    )

    # LLM semaphore (shared across all pipeline runs)
    app.state.llm_semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)

    # Prompt template loader
    app.state.prompt_loader = PromptLoader(template_dir="app/prompts")

    # Pipeline orchestrator
    app.state.orchestrator = PipelineOrchestrator(
        steps=build_step_registry(app.state),
        event_bus=RedisEventBus(app.state.redis),
        report_repository=ReportRepository(app.state.db_pool),
        llm_semaphore=app.state.llm_semaphore
    )

    # Background jobs
    cleanup_task = asyncio.create_task(run_cleanup_job(app.state.db_pool))
    metrics_task = asyncio.create_task(run_metrics_aggregation_job(app.state.db_pool))

    # Run Alembic migrations
    await run_migrations(settings.database_url)

    yield  # ← application runs here

    # ── Shutdown ─────────────────────────────────────────────
    cleanup_task.cancel()
    metrics_task.cancel()
    await app.state.db_pool.close()
    await app.state.redis.close()
```

### 2.3 `app/config.py` — Settings

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://stocklens:password@db:5432/stocklens"

    # Redis
    redis_url: str = "redis://redis:6379/0"

    # Ollama
    ollama_url: str = "http://ollama:11434"
    default_llm_model: str = "mistral:7b-instruct"

    # Pipeline
    max_concurrent_llm_calls: int = 3
    pipeline_timeout_seconds: int = 90
    max_articles_per_run: int = 20
    news_window_days: int = 30

    # Rate limiting
    rate_limit_requests_per_window: int = 10
    rate_limit_window_seconds: int = 60

    # Data retention
    run_retention_hours: int = 24

    # Environment
    environment: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### 2.4 `app/api/routers/analyze.py`

```python
router = APIRouter(tags=["analysis"])

@router.post("/analyze", status_code=202, response_model=AnalyzeResponse)
async def trigger_analysis(
    request: AnalyzeRequest,
    raw_request: Request,
    orchestrator: PipelineOrchestrator = Depends(get_orchestrator),
    rate_limiter: RateLimiter = Depends(get_rate_limiter),
    llm_provider: LLMProvider = Depends(get_llm_provider),   # request-scoped
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings)
):
    ip = get_client_ip(raw_request)

    # Rate limit check
    allowed, window_count = await rate_limiter.check(ip, endpoint="POST /api/v1/analyze")
    if not allowed:
        await log_rate_limit_event(ip, endpoint="POST /api/v1/analyze", window_count=window_count)
        raise HTTPException(
            status_code=429,
            headers={"Retry-After": str(settings.rate_limit_window_seconds)},
            detail={"error_code": "RATE_LIMIT_EXCEEDED", "message": "Too many requests", "retry_after": settings.rate_limit_window_seconds}
        )

    # Idempotency
    run_id = await get_or_create_run(redis, ip, request.ticker, orchestrator, llm_provider)

    return AnalyzeResponse(run_id=run_id, status="accepted")
```

### 2.5 `app/api/routers/stream.py`

```python
@router.get("/analyze/stream/{run_id}")
async def stream_pipeline_events(
    run_id: UUID,
    redis: Redis = Depends(get_redis)
):
    # Validate run exists
    if not await run_exists(redis, run_id):
        raise HTTPException(status_code=404, detail={"error_code": "RUN_NOT_FOUND"})

    async def event_generator():
        # Replay buffered events first (handle reconnects)
        buffered = await redis.lrange(f"pipeline:events:{run_id}", 0, -1)
        for raw_event in buffered:
            yield f"data: {raw_event}\n\n"

        # Check if pipeline already complete
        if await redis.exists(f"run:complete:{run_id}"):
            yield f"data: {json.dumps({'event_type': 'stream_end'})}\n\n"
            return

        # Subscribe to live events
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"pipeline:events:{run_id}")
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
                    event = json.loads(message["data"])
                    if event.get("event_type") in ("pipeline_complete", "pipeline_failed", "pipeline_timeout"):
                        break
        finally:
            await pubsub.unsubscribe(f"pipeline:events:{run_id}")
            await pubsub.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering for SSE
            "Connection": "keep-alive"
        }
    )
```

---

## 3. Frontend Module Structure — Detailed

### 3.1 State Management Architecture

The frontend state is organized into three Zustand slices plus local React state for component-specific concerns.

**`store/analysisSlice.ts`**

```typescript
interface AnalysisState {
  // Current run
  runId: string | null;
  ticker: string;
  status: 'idle' | 'loading' | 'streaming' | 'complete' | 'failed' | 'timeout';

  // Step events (append-only as SSE arrives)
  stepEvents: StepEvent[];

  // Derived panel data (computed from stepEvents)
  company: CompanyInfo | null;
  marketData: MarketData | null;
  priceHistory: PriceHistory | null;
  news: NewsSection | null;
  sentiment: SentimentSection | null;
  events: EventsSection | null;
  insights: InsightSection | null;
  dataSources: DataSource[];

  // Partial report state
  partialDataNotices: string[];
  errorNotices: string[];
  completeness: 'complete' | 'partial' | 'minimal' | null;

  // Actions
  startAnalysis: (ticker: string) => void;
  appendStepEvent: (event: StepEvent) => void;
  setPipelineComplete: (event: PipelineCompleteEvent) => void;
  setPipelineFailed: (event: PipelineFailedEvent) => void;
  reset: () => void;
}
```

**`store/settingsSlice.ts`**

```typescript
interface SettingsState {
  // OpenAI key — in-memory ONLY; never written to localStorage
  openAiKey: string;
  openAiKeyStatus: 'unset' | 'set' | 'invalid';
  activeModel: string;   // e.g. "mistral:7b-instruct" | "gpt-4o-mini"

  setOpenAiKey: (key: string) => void;
  clearOpenAiKey: () => void;
  markKeyInvalid: () => void;
}
```

**`store/uiSlice.ts`**

```typescript
interface UIState {
  panelExpansion: Record<PanelId, boolean>;
  activeTimeframe: '1M' | '3M' | '6M' | '1Y';
  reasoningViewerExpanded: boolean;

  togglePanel: (panelId: PanelId) => void;
  setTimeframe: (tf: ActiveTimeframe) => void;
  toggleReasoningViewer: () => void;
}
```

**Panel ID enum:**

```typescript
type PanelId =
  | 'stock_overview'
  | 'price_chart'
  | 'news_summary'
  | 'sentiment'
  | 'events'
  | 'insights'
  | 'data_sources'
  | 'reasoning_viewer';
```

---

### 3.2 `hooks/useAnalysis.ts` — Core Analysis Orchestration Hook

This hook encapsulates the full lifecycle: POST to backend → receive `run_id` → open SSE stream → dispatch events to the store.

```typescript
export function useAnalysis() {
  const { startAnalysis, appendStepEvent, setPipelineComplete, setPipelineFailed, reset } =
    useAnalysisStore();
  const { openAiKey, markKeyInvalid } = useSettingsStore();
  const { openSSE, closeSSE } = useSSEStream();

  const analyze = useCallback(async (ticker: string) => {
    reset();
    startAnalysis(ticker);

    // 1. POST /api/v1/analyze
    let runId: string;
    try {
      const response = await api.triggerAnalysis(ticker, openAiKey || undefined);
      runId = response.run_id;
    } catch (error) {
      if (isRateLimitError(error)) {
        setPipelineFailed({ reason: 'Rate limit exceeded. Please wait before trying again.' });
      } else {
        setPipelineFailed({ reason: 'Failed to start analysis. Please try again.' });
      }
      return;
    }

    // 2. Open SSE stream
    openSSE(`/api/v1/analyze/stream/${runId}`, {
      onEvent: (rawData: string) => {
        const event = parseSSEEvent(rawData);
        if (!event) return;

        switch (event.event_type) {
          case 'step_event':
            appendStepEvent(event as StepEvent);
            break;
          case 'pipeline_complete':
            setPipelineComplete(event as PipelineCompleteEvent);
            closeSSE();
            break;
          case 'pipeline_failed':
            // Check for OpenAI key invalidation signal
            if ((event as PipelineFailedEvent).failed_step === 'openai_auth') {
              markKeyInvalid();
            }
            setPipelineFailed(event as PipelineFailedEvent);
            closeSSE();
            break;
          case 'pipeline_timeout':
            setPipelineFailed({ reason: 'Analysis timed out. Please try again.' });
            closeSSE();
            break;
        }
      },
      onError: () => {
        setPipelineFailed({ reason: 'Connection to analysis stream was lost.' });
      }
    });
  }, [openAiKey]);

  return { analyze };
}
```

### 3.3 `hooks/useSSEStream.ts` — SSE Connection Management

```typescript
export function useSSEStream() {
  const readerRef = useRef<ReadableStreamDefaultReader | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const openSSE = useCallback((url: string, handlers: SSEHandlers) => {
    const controller = new AbortController();
    abortControllerRef.current = controller;

    (async () => {
      try {
        const response = await fetch(url, {
          signal: controller.signal,
          headers: { Accept: 'text/event-stream' }
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

          // SSE frames are separated by \n\n
          const frames = buffer.split('\n\n');
          buffer = frames.pop() ?? '';  // last partial frame stays in buffer

          for (const frame of frames) {
            const dataLine = frame.split('\n').find(l => l.startsWith('data: '));
            if (dataLine) {
              handlers.onEvent(dataLine.slice(6));  // strip "data: "
            }
          }
        }
      } catch (error) {
        if ((error as Error).name !== 'AbortError') {
          handlers.onError?.();
        }
      }
    })();
  }, []);

  const closeSSE = useCallback(() => {
    abortControllerRef.current?.abort();
    readerRef.current?.cancel();
  }, []);

  // Clean up on unmount
  useEffect(() => () => closeSSE(), [closeSSE]);

  return { openSSE, closeSSE };
}
```

---

### 3.4 Component Architecture

#### Panel Component Hierarchy

```
ReportGrid (Client Component)
├── ReasoningViewer
│   └── StepEntry × 9
├── StockOverviewPanel
│   └── Panel (base shell)
│       └── StockOverviewContent | PanelSkeleton | ErrorState
├── PriceTrendChart
│   └── Panel
│       └── RechartsLineChart | PanelSkeleton | ErrorState
├── NewsSummaryPanel
│   └── Panel
│       └── ArticleCard × n | PanelSkeleton | ErrorState
├── SentimentPanel
│   └── Panel
│       └── SentimentBar + DominantLabel | PanelSkeleton | ErrorState
├── EventsPanel
│   └── Panel
│       └── EventCard × n | PanelSkeleton | EmptyState
├── InsightPanel
│   └── Panel
│       └── InsightSections + Disclaimer | PanelSkeleton | ErrorState
└── DataSourcesPanel
    └── Panel (collapsible)
        └── SourceList
```

#### `Panel.tsx` — Base Collapsible Panel Shell

```typescript
interface PanelProps {
  id: PanelId;
  title: string;
  status: 'loading' | 'populated' | 'partial' | 'error' | 'unavailable';
  partialNotice?: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}

export function Panel({ id, title, status, partialNotice, defaultExpanded = true, children }: PanelProps) {
  const { panelExpansion, togglePanel } = useUIStore();
  const isExpanded = panelExpansion[id] ?? defaultExpanded;

  return (
    <section
      aria-labelledby={`panel-title-${id}`}
      className="rounded-lg border border-neutral-200 bg-white shadow-sm"
    >
      <div
        className="flex items-center justify-between px-4 py-3 cursor-pointer"
        onClick={() => togglePanel(id)}
        role="button"
        aria-expanded={isExpanded}
        aria-controls={`panel-content-${id}`}
        tabIndex={0}
        onKeyDown={(e) => e.key === 'Enter' && togglePanel(id)}
      >
        <h2 id={`panel-title-${id}`} className="font-semibold text-sm text-neutral-800">
          {title}
        </h2>
        <div className="flex items-center gap-2">
          <StatusIndicator status={status} />
          <ChevronIcon expanded={isExpanded} />
        </div>
      </div>

      {partialNotice && (
        <div role="alert" className="px-4 py-1 text-xs text-amber-700 bg-amber-50 border-t border-amber-100">
          {partialNotice}
        </div>
      )}

      <div
        id={`panel-content-${id}`}
        role="region"
        className={isExpanded ? 'block' : 'hidden'}
      >
        {children}
      </div>
    </section>
  );
}
```

---

### 3.5 Navigation Architecture

The application is a Next.js App Router SPA with two routes:

| Route | Type | Description |
|---|---|---|
| `/` | Client Component (with RSC shell) | Playground — ticker input + all panels |
| `/docs` | React Server Component (static) | API documentation page |

**Route structure in `app/`:**

`app/page.tsx` — RSC shell that renders `<PlaygroundClient />` (a `'use client'` component). The RSC shell provides the `<head>` metadata, the non-financial-advice disclaimer as a server-rendered element, and the page skeleton before client JS hydrates.

`app/docs/page.tsx` — Pure RSC. Renders a static API documentation layout with code blocks. No client JS needed. Generated at build time (`generateStaticParams`).

**No client-side routing** between these two pages is needed. The Settings modal is rendered as a portal overlay on `/`, not a separate route. The API docs link opens `/docs` — the user navigates there with a standard anchor tag.

---

### 4. Design System Architecture

#### Tailwind Configuration

```typescript
// tailwind.config.ts
const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Semantic color tokens — defined as CSS custom properties
        // These are set via shadcn/ui's CSS variable convention
        brand: {
          50:  'hsl(var(--brand-50))',
          500: 'hsl(var(--brand-500))',
          900: 'hsl(var(--brand-900))',
        },
        sentiment: {
          positive: 'hsl(var(--sentiment-positive))',
          neutral:  'hsl(var(--sentiment-neutral))',
          negative: 'hsl(var(--sentiment-negative))',
        }
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-jetbrains-mono)', 'monospace'],
      }
    }
  }
};
```

#### Semantic Color Tokens

Sentiment colors are defined as semantic tokens, not raw Tailwind colors. This ensures they can be changed without hunting through component files, and they automatically support a future dark mode.

```css
/* app/globals.css */
:root {
  --brand-50:  210 100% 97%;
  --brand-500: 210 100% 50%;
  --brand-900: 210 100% 20%;

  --sentiment-positive: 142 76% 36%;
  --sentiment-neutral:  43 96% 56%;
  --sentiment-negative: 0 84% 60%;

  --background: 0 0% 100%;
  --foreground: 222.2 84% 4.9%;
  --border:     214.3 31.8% 91.4%;
}
```

#### Price Direction Convention

Price direction (up/down) is conveyed via BOTH color AND a directional arrow icon — never via color alone (WCAG 2.1 AA requirement). The `StatusIndicator` component always pairs a color with an icon and a text label.

```typescript
// components/ui/PriceDirection.tsx
export function PriceDirection({ changePct }: { changePct: number }) {
  const isUp = changePct > 0;
  const isFlat = changePct === 0;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 font-medium",
        isUp ? "text-sentiment-positive" : isFlat ? "text-neutral-500" : "text-sentiment-negative"
      )}
      aria-label={`${isUp ? 'Up' : isFlat ? 'Unchanged' : 'Down'} ${Math.abs(changePct).toFixed(2)} percent`}
    >
      {isUp ? <ArrowUpIcon aria-hidden="true" /> : isFlat ? <MinusIcon aria-hidden="true" /> : <ArrowDownIcon aria-hidden="true" />}
      <span>{isUp ? '+' : ''}{changePct.toFixed(2)}%</span>
    </span>
  );
}
```

---

### 5. Theming System

Theming is implemented via CSS custom properties only (no runtime theme switching in MVP). All colors, radii, and spacing tokens are CSS variables. `shadcn/ui`'s convention is followed.

**Dark mode (Phase 2):** Dark mode is implemented by toggling `class="dark"` on `<html>`. All semantic color tokens have dark-mode variants in `globals.css` under `@media (prefers-color-scheme: dark)`. This is set up from the start to avoid retrofitting.

```css
@media (prefers-color-scheme: dark) {
  :root {
    --background: 222.2 84% 4.9%;
    --foreground: 210 40% 98%;
    --sentiment-positive: 142 76% 50%;
    --sentiment-neutral:  43 96% 70%;
    --sentiment-negative: 0 84% 70%;
  }
}
```

---

### 6. Accessibility Strategy

**Requirement baseline:** WCAG 2.1 AA.

#### Implementation Checklist

| Requirement | Implementation |
|---|---|
| Color not sole differentiator | All sentiment labels and price direction use icon + text + color |
| Chart data accessible | `PriceTrendChart` renders a visually-hidden `<table>` with OHLCV data alongside the SVG chart |
| All interactive elements keyboard navigable | `Panel` collapse toggle uses `role="button"` + `tabIndex={0}` + `onKeyDown` handler |
| Focus management on modal open | `SettingsModal` uses `@radix-ui/react-dialog` which handles focus trap and `aria-modal` automatically |
| ARIA labels on icons | All `lucide-react` icons that convey meaning use `aria-label`; decorative icons use `aria-hidden="true"` |
| Live regions for streaming updates | `ReasoningViewer` uses `aria-live="polite"` so screen readers announce new steps without interrupting |
| Form error announcements | `TickerInput` validation errors use `role="alert"` and `aria-describedby` linking input to error message |
| Skip navigation | A visually-hidden `<a href="#main-content">Skip to main content</a>` is the first focusable element |
| Minimum touch targets | All interactive elements are `min-h-[44px] min-w-[44px]` via Tailwind |
| Sufficient color contrast | All text/background combinations checked to ≥ 4.5:1 ratio (WCAG AA) |

#### Chart Accessibility Pattern

```typescript
// components/panels/PriceTrendChart.tsx
export function PriceTrendChart({ priceHistory }: Props) {
  return (
    <div>
      {/* Visual chart (aria-hidden — data is in the table below) */}
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={priceHistory.dataPoints}>
            <Line type="monotone" dataKey="close" stroke="hsl(var(--brand-500))" dot={false} />
            <XAxis dataKey="date" />
            <YAxis domain={['auto', 'auto']} />
            <Tooltip />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Accessible data table — visually hidden but available to screen readers */}
      <div className="sr-only">
        <table>
          <caption>Historical closing prices for {priceHistory.ticker}</caption>
          <thead>
            <tr><th scope="col">Date</th><th scope="col">Closing Price</th></tr>
          </thead>
          <tbody>
            {priceHistory.dataPoints.map(point => (
              <tr key={point.date}>
                <td>{formatDate(point.date)}</td>
                <td>{formatPrice(point.close)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

---

### 7. Localization Readiness

MVP is English-only. The architecture is structured to support localization in Phase 3 with minimal refactoring.

**Strategy:**

- All user-facing strings in components are sourced from a `lib/strings.ts` constants file (not hard-coded inline). This provides a single extraction point for i18n.
- Numeric formatting (prices, percentages, large numbers) uses `Intl.NumberFormat` throughout `lib/formatters.ts` — locale-aware from day one.
- Date formatting uses `Intl.DateTimeFormat` — locale-aware from day one.
- The disclaimer text is stored as a domain constant (not a UI string), so it can be separately managed for localized legal review.

```typescript
// lib/formatters.ts
export function formatPrice(value: number, currency = 'USD', locale = 'en-US'): string {
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
}

export function formatLargeNumber(value: number, locale = 'en-US'): string {
  return new Intl.NumberFormat(locale, {
    notation: 'compact',
    maximumFractionDigits: 2
  }).format(value);
}
```

**i18n library (Phase 3):** `next-intl` is the planned library. Adding it requires:

1. Wrapping the root layout with `NextIntlClientProvider`.
2. Extracting `lib/strings.ts` constants into locale JSON files.
3. Replacing `strings.X` calls with `t('X')` from `useTranslations()`.

---

### 8. Error State UX Patterns

Every panel that displays data has three defined non-populated states:

#### 8.1 Loading State (skeleton)

Shown immediately when a pipeline starts and before the corresponding step event arrives.

```typescript
// components/ui/PanelSkeleton.tsx
export function PanelSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="p-4 space-y-3" aria-busy="true" aria-label="Loading data">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-4 bg-neutral-100 rounded animate-pulse" style={{ width: `${70 + (i % 3) * 10}%` }} />
      ))}
    </div>
  );
}
```

#### 8.2 Partial Data State

Shown when a step partially succeeded (e.g., some articles failed summarization).

The `Panel` component's `partialNotice` prop renders an amber banner beneath the panel header:

```
⚠ Some data could not be retrieved. Results may be incomplete.
```

Individual panel components inspect their data and render inline "N/A" or "unavailable" labels for missing fields — they do not blank out the entire panel.

#### 8.3 Error / Unavailable State

Shown when a step completely failed. The panel still renders (not removed from DOM) but shows an error state card.

```typescript
// components/ui/ErrorState.tsx
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="p-4 flex flex-col items-center gap-2 text-center">
      <AlertCircleIcon className="w-6 h-6 text-sentiment-negative" aria-hidden="true" />
      <p className="text-sm text-neutral-600">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="text-xs text-brand-500 underline">
          Try again
        </button>
      )}
    </div>
  );
}
```

**Error message sources:** All user-facing error messages come from `lib/strings.ts` — never from raw error objects or API error messages. API error codes are mapped to friendly strings:

```typescript
// lib/strings.ts
export const ERROR_MESSAGES: Record<string, string> = {
  MARKET_DATA_UNAVAILABLE: "Market data is not available for this ticker.",
  NEWS_RETRIEVAL_FAILED:   "News could not be retrieved at this time. Try again shortly.",
  SENTIMENT_UNAVAILABLE:   "Sentiment analysis is unavailable for this report.",
  INSIGHT_FAILED:          "AI insights could not be generated. Other data is still available.",
  TICKER_NOT_RESOLVABLE:   "This ticker could not be found. Check the symbol and try again.",
  RATE_LIMIT_EXCEEDED:     "Too many requests. Please wait a moment before trying again.",
  PIPELINE_TIMEOUT:        "Analysis took too long to complete. Please try again.",
  GENERIC_ERROR:           "Something went wrong. Please try again.",
};
```

---

### 9. Empty State UX Patterns

#### First Load (Pre-Analysis)

The playground page in pre-analysis state shows:

- The ticker input centered on the page
- Subtitle: "AI-powered stock research — just enter a ticker to begin"
- Inline hint text below input: `Try: AAPL, TSLA, NVDA, MSFT`
- No panels are rendered in the DOM — they are conditionally rendered only after `runId` is set in the store

```typescript
// app/page.tsx (Client Component section)
export default function PlaygroundClient() {
  const { runId, status } = useAnalysisStore();

  return (
    <main id="main-content">
      <TickerInput />

      {runId && <ReasoningViewer />}

      {runId && (
        <ReportGrid />   // renders all panels conditionally based on step events
      )}

      {!runId && <EmptyState />}
    </main>
  );
}
```

#### Empty News State

```typescript
// Rendered inside NewsSummaryPanel when news.articles.length === 0
<div className="p-6 text-center">
  <NewspaperIcon className="mx-auto w-8 h-8 text-neutral-300 mb-2" aria-hidden="true" />
  <p className="text-sm text-neutral-500">No recent news articles found for {ticker}.</p>
  <p className="text-xs text-neutral-400 mt-1">Retrieval window: last {windowDays} days</p>
</div>
```

#### Empty Events State

```typescript
<p className="p-4 text-sm text-neutral-500 italic">
  No significant events identified in the current news window.
</p>
```

---

### 10. Reasoning Viewer Component

The `ReasoningViewer` is the most interaction-intensive component. It receives step events from the Zustand store as they arrive from the SSE stream and animates each step entry into view.

```typescript
// components/playground/ReasoningViewer.tsx
const STEP_DESCRIPTIONS: Record<string, string> = {
  TickerValidator:        "Validating ticker and resolving company information",
  MarketDataCollector:    "Fetching current price, volume, and financial ratios",
  NewsRetriever:          "Retrieving recent news articles",
  NewsDeduplicator:       "Removing duplicate articles covering the same events",
  ArticleSummarizer:      "Summarizing each article using AI",
  SentimentClassifier:    "Classifying the sentiment of each article",
  EventExtractor:         "Identifying key business events from the news",
  InsightGenerator:       "Generating AI research overview",
  ReportAssembler:        "Assembling the final report",
};

export function ReasoningViewer() {
  const { stepEvents, status } = useAnalysisStore();
  const { reasoningViewerExpanded, toggleReasoningViewer } = useUIStore();

  return (
    <section aria-label="Analysis reasoning steps" aria-live="polite">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-neutral-700">Agent Reasoning</h2>
        <button
          onClick={toggleReasoningViewer}
          aria-expanded={reasoningViewerExpanded}
          className="text-xs text-neutral-400 hover:text-neutral-600"
        >
          {reasoningViewerExpanded ? 'Collapse' : 'Expand'}
        </button>
      </div>

      {reasoningViewerExpanded && (
        <ol className="space-y-1">
          {stepEvents.map((event, index) => (
            <StepEntry key={event.step_name} event={event} animationDelay={index * 50} />
          ))}
          {status === 'streaming' && <StepEntryPending />}
        </ol>
      )}
    </section>
  );
}

function StepEntry({ event, animationDelay }: { event: StepEvent; animationDelay: number }) {
  return (
    <li
      className="flex items-start gap-2 text-xs animate-slide-in-left"
      style={{ animationDelay: `${animationDelay}ms` }}
      aria-label={`Step ${event.step_index}: ${event.step_name} — ${event.status}`}
    >
      <StepStatusIcon status={event.status} />
      <div>
        <span className="font-medium">{STEP_DESCRIPTIONS[event.step_name]}</span>
        {event.status === 'failed' && event.reason && (
          <span className="text-sentiment-negative ml-1">({event.reason})</span>
        )}
        {event.duration_ms && (
          <span className="text-neutral-400 ml-1">{event.duration_ms}ms</span>
        )}
      </div>
    </li>
  );
}
```

---

### 11. `lib/api.ts` — Typed Backend API Client

```typescript
const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? '';

export const api = {
  async triggerAnalysis(ticker: string, openAiKey?: string): Promise<AnalyzeResponse> {
    const response = await fetch(`${BASE_URL}/api/v1/analyze`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(openAiKey ? { 'X-OpenAI-Key': openAiKey } : {})
      },
      body: JSON.stringify({ ticker })
    });

    if (response.status === 429) {
      const retryAfter = response.headers.get('Retry-After');
      throw new RateLimitError(parseInt(retryAfter ?? '60'));
    }
    if (!response.ok) {
      throw new APIError(response.status, await response.json());
    }
    return response.json();
  },

  async getPastResult(runId: string): Promise<AnalysisReport> {
    const response = await fetch(`${BASE_URL}/api/v1/results/${runId}`);
    if (response.status === 404) throw new NotFoundError(runId);
    if (!response.ok) throw new APIError(response.status, await response.json());
    return response.json();
  },

  async getMetrics(): Promise<SystemMetrics> {
    const response = await fetch(`${BASE_URL}/api/v1/metrics`);
    if (!response.ok) throw new APIError(response.status, await response.json());
    return response.json();
  }
};
```

---

### 12. Reusable Component Strategy

Components are divided into three tiers:

| Tier | Location | Description |
|---|---|---|
| **Primitive UI** | `components/ui/` | Stateless, domain-agnostic (Panel, PanelSkeleton, StatusIndicator, ErrorState, Disclaimer) |
| **Domain UI** | `components/panels/` | Stateful via Zustand; domain-specific (StockOverviewPanel, SentimentPanel, etc.) |
| **Page-level** | `components/playground/`, `components/settings/` | Composed from domain UI + primitive UI; orchestrate user flows |

**Rule:** Primitive UI components have zero Zustand dependencies — they receive all data as props. This makes them independently testable and reusable. Domain UI components read from the store directly.

---

### 13. Settings Modal — OpenAI Key Handling

```typescript
// components/settings/SettingsModal.tsx
export function SettingsModal() {
  const { openAiKey, openAiKeyStatus, setOpenAiKey, clearOpenAiKey } = useSettingsStore();
  const [inputValue, setInputValue] = useState('');

  // Never pre-populate the input from the store (key is write-only in the UI)
  const handleSave = () => {
    if (!inputValue.startsWith('sk-')) {
      // Basic format validation — not a security check
      return;
    }
    setOpenAiKey(inputValue);
    setInputValue('');
  };

  return (
    <Dialog>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <label htmlFor="openai-key" className="text-sm font-medium">
            OpenAI API Key (optional)
          </label>
          <input
            id="openai-key"
            type="password"
            autoComplete="off"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="sk-..."
            className="w-full border rounded px-3 py-2 text-sm"
          />

          {openAiKeyStatus === 'set' && (
            <p className="text-xs text-green-600">
              ✓ API key active for this session
            </p>
          )}
          {openAiKeyStatus === 'invalid' && (
            <p role="alert" className="text-xs text-red-600">
              ✗ API key was rejected. Analysis used the local model instead.
            </p>
          )}

          <p className="text-xs text-neutral-500">
            Your key is used only for this browser session and is never stored.
          </p>

          <div className="flex gap-2">
            <button onClick={handleSave} className="btn-primary text-sm">Save</button>
            {openAiKeyStatus === 'set' && (
              <button onClick={clearOpenAiKey} className="btn-ghost text-sm">Clear</button>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

---

### 14. Technical Debt Mitigation Strategy

| Risk | Mitigation |
|---|---|
| `yfinance` unofficial API breaks | `MarketDataProvider` interface isolates the dependency; swap to Alpha Vantage adapter in one file |
| LLM prompt drift (model update changes output format) | Prompt templates are versioned in `app/prompts/`; JSON output validation via Pydantic catches regressions before they reach users |
| SimHash dedup accuracy degrades with more sources (Phase 2) | Algorithm is isolated in `news_deduplicator.py`; can be replaced with embedding similarity without touching orchestrator |
| Zustand store grows complex as features are added | Slice pattern isolates concerns; each slice is independently testable |
| SSE reconnect logic misses events | Redis List replay buffer is the safety net; all events are replayed on reconnect regardless of when the client connected |
| Ollama version updates break API contract | Pin Ollama Docker image to a specific version tag; update in a controlled release cycle |
| Report `jsonb` schema evolves over phases | `report_data` is versioned with a `schema_version` field; the reader always checks version before parsing |
