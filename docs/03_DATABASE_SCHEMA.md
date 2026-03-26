# 03_DATABASE_SCHEMA.md — StockLens AI

---

## 1. Schema Design Philosophy

The data model is intentionally minimal for MVP. The core persistence requirement is:

1. Store completed analysis run results so the `GET /api/v1/results/{run_id}` endpoint can retrieve them within the 24-hour retention window.
2. Store step-level execution metadata for observability and debugging.
3. Store aggregated system metrics for the `GET /api/v1/metrics` endpoint.
4. Maintain an audit trail for all pipeline executions (complete, failed, timed-out).

**Design decisions:**

- The assembled report is stored as a single `jsonb` column (`report_data`). The report schema is a Pydantic model; storing it as `jsonb` avoids a deeply normalized schema for report sections that would require complex joins on read without adding query value in MVP. Individual fields within `jsonb` are extracted via generated columns where query filtering is needed (ticker, status).
- No ORM. All queries use raw `asyncpg` with parameterized queries. This is intentional for performance transparency and to avoid ORM abstraction leaking into the domain layer.
- `BIGSERIAL` surrogate PKs for internal join efficiency; `UUID` business keys for external API surface.
- `updated_at` triggers maintain audit timestamps without application-layer overhead.

---

## 2. Complete Entity Definitions

### 2.1 `analysis_runs`

Primary table. One row per triggered analysis pipeline execution.

```sql
CREATE TABLE analysis_runs (
    id                  BIGSERIAL       PRIMARY KEY,
    run_id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    ticker              VARCHAR(12)     NOT NULL,
    status              VARCHAR(20)     NOT NULL DEFAULT 'accepted',
    -- status: accepted | in_progress | complete | failed | timed_out
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    duration_ms         INTEGER,
    -- duration_ms: set at completion; completed_at - started_at in ms

    llm_provider        VARCHAR(20)     NOT NULL DEFAULT 'ollama',
    -- llm_provider: ollama | openai
    llm_model           VARCHAR(80),
    -- e.g. 'mistral:7b-instruct', 'gpt-4o-mini'

    ip_address          INET,
    -- stored for rate limit audit; not associated with any user identity

    report_data         JSONB,
    -- null until status = complete; full AnalysisReport JSON

    error_message       TEXT,
    -- populated on status = failed | timed_out

    steps_total         SMALLINT        NOT NULL DEFAULT 9,
    steps_completed     SMALLINT        NOT NULL DEFAULT 0,
    steps_failed        SMALLINT        NOT NULL DEFAULT 0,

    is_deleted          BOOLEAN         NOT NULL DEFAULT FALSE,
    -- soft delete; TTL cleanup job sets this before hard DELETE
    deleted_at          TIMESTAMPTZ,

    CONSTRAINT analysis_runs_run_id_unique UNIQUE (run_id),
    CONSTRAINT analysis_runs_status_check CHECK (
        status IN ('accepted', 'in_progress', 'complete', 'failed', 'timed_out')
    ),
    CONSTRAINT analysis_runs_llm_provider_check CHECK (
        llm_provider IN ('ollama', 'openai')
    ),
    CONSTRAINT analysis_runs_steps_completed_range CHECK (
        steps_completed >= 0 AND steps_completed <= steps_total
    ),
    CONSTRAINT analysis_runs_steps_failed_range CHECK (
        steps_failed >= 0 AND steps_failed <= steps_total
    ),
    CONSTRAINT analysis_runs_duration_positive CHECK (
        duration_ms IS NULL OR duration_ms >= 0
    ),
    CONSTRAINT analysis_runs_ticker_format CHECK (
        ticker ~ '^[A-Z]{1,5}(\.[A-Z]{1,3})?$'
    )
);
```

**Column notes:**

- `ticker` is stored in normalized uppercase (enforced at application layer and as a CHECK constraint).
- `ip_address` uses the PostgreSQL `INET` type for efficient storage (4 bytes IPv4, 16 bytes IPv6) and future IP-range queries.
- `report_data` is `NULL` until the pipeline reaches the `ReportAssembler` step successfully. The column being `NULL` while `status = 'in_progress'` is a valid, expected state.
- `is_deleted` / `deleted_at` support soft delete; the TTL cleanup job soft-deletes first, then hard-deletes after a 1-hour grace period (allows forensic inspection of runs that just passed the TTL boundary).

---

### 2.2 `pipeline_steps`

One row per step per run. Provides step-level granularity for observability and debugging. This table is write-once per step (inserted when a step transitions to `in_progress`; updated once to `complete` or `failed`).

```sql
CREATE TABLE pipeline_steps (
    id                  BIGSERIAL       PRIMARY KEY,
    run_id              UUID            NOT NULL,
    step_index          SMALLINT        NOT NULL,
    -- 1-9, matching the PipelineOrchestrator step order
    step_name           VARCHAR(60)     NOT NULL,
    -- e.g. 'TickerValidator', 'MarketDataCollector'
    status              VARCHAR(20)     NOT NULL DEFAULT 'pending',
    -- pending | in_progress | complete | failed | skipped
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    duration_ms         INTEGER,

    input_summary       JSONB,
    -- lightweight snapshot of what this step received; NOT full data
    -- e.g. { "ticker": "AAPL", "article_count": 12 }
    output_summary      JSONB,
    -- lightweight snapshot of what this step produced
    -- e.g. { "articles_after_dedup": 8, "sentiment": "positive" }
    error_message       TEXT,
    error_code          VARCHAR(60),
    -- e.g. 'EXTERNAL_PROVIDER_TIMEOUT', 'LLM_JSON_PARSE_ERROR'

    retry_count         SMALLINT        NOT NULL DEFAULT 0,

    CONSTRAINT pipeline_steps_run_fk FOREIGN KEY (run_id)
        REFERENCES analysis_runs (run_id)
        ON DELETE CASCADE,
    CONSTRAINT pipeline_steps_unique_step_per_run
        UNIQUE (run_id, step_index),
    CONSTRAINT pipeline_steps_status_check CHECK (
        status IN ('pending', 'in_progress', 'complete', 'failed', 'skipped')
    ),
    CONSTRAINT pipeline_steps_step_index_range CHECK (
        step_index BETWEEN 1 AND 9
    ),
    CONSTRAINT pipeline_steps_duration_positive CHECK (
        duration_ms IS NULL OR duration_ms >= 0
    )
);
```

**Note on `input_summary` / `output_summary`:** These are NOT full data copies. They are lightweight diagnostic snapshots (counts, flags, key identifiers) used for debugging without requiring full report deserialization. Full data is in `analysis_runs.report_data`.

---

### 2.3 `system_metrics_hourly`

Aggregated metrics written by the background metrics job every hour. Used by the `GET /api/v1/metrics` endpoint. Pre-aggregation avoids expensive `COUNT` / `AVG` queries over `analysis_runs` on every API call.

```sql
CREATE TABLE system_metrics_hourly (
    id                      BIGSERIAL       PRIMARY KEY,
    bucket_start            TIMESTAMPTZ     NOT NULL,
    -- truncated to the hour: DATE_TRUNC('hour', NOW())
    bucket_end              TIMESTAMPTZ     NOT NULL,

    runs_total              INTEGER         NOT NULL DEFAULT 0,
    runs_complete           INTEGER         NOT NULL DEFAULT 0,
    runs_failed             INTEGER         NOT NULL DEFAULT 0,
    runs_timed_out          INTEGER         NOT NULL DEFAULT 0,

    -- duration percentiles (ms)
    p50_duration_ms         INTEGER,
    p95_duration_ms         INTEGER,
    p99_duration_ms         INTEGER,

    -- unique tickers analyzed in this hour
    unique_tickers          INTEGER         NOT NULL DEFAULT 0,

    -- average articles retrieved per run
    avg_articles_per_run    NUMERIC(6,2),

    -- rate limit events
    rate_limit_hits         INTEGER         NOT NULL DEFAULT 0,

    -- step failure counts (denormalized for fast reads)
    step_failures_json      JSONB,
    -- e.g. { "MarketDataCollector": 3, "SentimentClassifier": 1 }

    recorded_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT system_metrics_hourly_bucket_unique UNIQUE (bucket_start),
    CONSTRAINT system_metrics_hourly_bucket_order CHECK (
        bucket_end > bucket_start
    ),
    CONSTRAINT system_metrics_hourly_runs_non_negative CHECK (
        runs_total >= 0 AND runs_complete >= 0 AND
        runs_failed >= 0 AND runs_timed_out >= 0
    )
);
```

---

### 2.4 `ticker_resolution_cache`

Persists ticker-to-company resolution results to avoid repeated yfinance calls for the same ticker across runs. This is a write-through cache with TTL enforcement in the application layer (Redis primary, PostgreSQL as a fallback read source on Redis miss + cold start).

```sql
CREATE TABLE ticker_resolution_cache (
    id                  BIGSERIAL       PRIMARY KEY,
    ticker              VARCHAR(12)     NOT NULL,
    company_name        VARCHAR(200),
    exchange            VARCHAR(20),
    sector              VARCHAR(100),
    industry            VARCHAR(100),
    currency            VARCHAR(10),
    country             VARCHAR(60),
    is_resolvable       BOOLEAN         NOT NULL DEFAULT TRUE,
    -- FALSE for delisted or unrecognized tickers; prevents repeated yfinance lookups
    resolved_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     NOT NULL,
    -- resolved_at + INTERVAL '1 hour' for resolvable tickers
    -- resolved_at + INTERVAL '24 hours' for non-resolvable (to suppress retries)

    CONSTRAINT ticker_resolution_cache_ticker_unique UNIQUE (ticker),
    CONSTRAINT ticker_resolution_cache_ticker_format CHECK (
        ticker ~ '^[A-Z]{1,12}(\.[A-Z]{1,3})?$'
    ),
    CONSTRAINT ticker_resolution_cache_expires_after_resolved CHECK (
        expires_at > resolved_at
    )
);
```

---

### 2.5 `rate_limit_log`

Append-only audit log of rate-limit events. Used for abuse detection and tuning of rate limit thresholds. The enforcement mechanism itself is Redis-based (sliding window); this table is a durable audit trail only.

```sql
CREATE TABLE rate_limit_log (
    id                  BIGSERIAL       PRIMARY KEY,
    ip_address          INET            NOT NULL,
    endpoint            VARCHAR(100)    NOT NULL,
    -- e.g. 'POST /api/v1/analyze'
    rejected_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    window_count        INTEGER,
    -- number of requests seen in the window at rejection time
    window_seconds      INTEGER
    -- the configured window duration
);
```

**Retention:** Rows older than 7 days are deleted by the cleanup job. This table is append-only; no updates.

---

## 3. Indexes

```sql
-- analysis_runs: primary lookup path for past-results API
CREATE UNIQUE INDEX idx_analysis_runs_run_id
    ON analysis_runs (run_id);

-- analysis_runs: ticker history queries (future feature; minimal cost now)
CREATE INDEX idx_analysis_runs_ticker_created
    ON analysis_runs (ticker, created_at DESC)
    WHERE is_deleted = FALSE;

-- analysis_runs: cleanup job efficiency
CREATE INDEX idx_analysis_runs_created_status
    ON analysis_runs (created_at, status)
    WHERE is_deleted = FALSE;

-- analysis_runs: partial index for in-progress runs (watchdog / monitoring)
CREATE INDEX idx_analysis_runs_in_progress
    ON analysis_runs (created_at)
    WHERE status IN ('accepted', 'in_progress') AND is_deleted = FALSE;

-- pipeline_steps: join from analysis_runs.run_id
CREATE INDEX idx_pipeline_steps_run_id
    ON pipeline_steps (run_id);

-- pipeline_steps: step failure analysis
CREATE INDEX idx_pipeline_steps_step_name_status
    ON pipeline_steps (step_name, status)
    WHERE status = 'failed';

-- system_metrics_hourly: time-range queries for API endpoint
CREATE INDEX idx_system_metrics_hourly_bucket
    ON system_metrics_hourly (bucket_start DESC);

-- ticker_resolution_cache: expiry cleanup
CREATE INDEX idx_ticker_resolution_cache_expires
    ON ticker_resolution_cache (expires_at)
    WHERE is_resolvable = TRUE;

-- rate_limit_log: cleanup job
CREATE INDEX idx_rate_limit_log_rejected_at
    ON rate_limit_log (rejected_at);

-- rate_limit_log: IP-based abuse investigation
CREATE INDEX idx_rate_limit_log_ip
    ON rate_limit_log (ip_address, rejected_at DESC);
```

---

## 4. `updated_at` Trigger

Applied to `analysis_runs` (the only table with mutable rows requiring audit timestamps):

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

Add `updated_at` column to `analysis_runs`:

```sql
ALTER TABLE analysis_runs
    ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

CREATE TRIGGER trg_analysis_runs_updated_at
    BEFORE UPDATE ON analysis_runs
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
```

---

## 5. Text-Based ER Diagram

```
analysis_runs
─────────────────────────────────────────────────
PK  id              BIGSERIAL
UK  run_id          UUID
    ticker          VARCHAR(12)
    status          VARCHAR(20)
    created_at      TIMESTAMPTZ
    started_at      TIMESTAMPTZ
    completed_at    TIMESTAMPTZ
    updated_at      TIMESTAMPTZ
    duration_ms     INTEGER
    llm_provider    VARCHAR(20)
    llm_model       VARCHAR(80)
    ip_address      INET
    report_data     JSONB
    error_message   TEXT
    steps_total     SMALLINT
    steps_completed SMALLINT
    steps_failed    SMALLINT
    is_deleted      BOOLEAN
    deleted_at      TIMESTAMPTZ
        │
        │ 1:N (run_id FK)
        ▼
pipeline_steps
─────────────────────────────────────────────────
PK  id              BIGSERIAL
FK  run_id          UUID → analysis_runs.run_id
    step_index      SMALLINT
    step_name       VARCHAR(60)
    status          VARCHAR(20)
    started_at      TIMESTAMPTZ
    completed_at    TIMESTAMPTZ
    duration_ms     INTEGER
    input_summary   JSONB
    output_summary  JSONB
    error_message   TEXT
    error_code      VARCHAR(60)
    retry_count     SMALLINT

ticker_resolution_cache         system_metrics_hourly
──────────────────────────      ──────────────────────────────
PK  id          BIGSERIAL       PK  id              BIGSERIAL
UK  ticker      VARCHAR(12)     UK  bucket_start    TIMESTAMPTZ
    company_name VARCHAR(200)       bucket_end       TIMESTAMPTZ
    exchange    VARCHAR(20)         runs_total       INTEGER
    sector      VARCHAR(100)        runs_complete    INTEGER
    industry    VARCHAR(100)        runs_failed      INTEGER
    currency    VARCHAR(10)         runs_timed_out   INTEGER
    country     VARCHAR(60)         p50_duration_ms  INTEGER
    is_resolvable BOOLEAN           p95_duration_ms  INTEGER
    resolved_at TIMESTAMPTZ         p99_duration_ms  INTEGER
    expires_at  TIMESTAMPTZ         unique_tickers   INTEGER
                                    avg_articles_per_run NUMERIC
rate_limit_log                      rate_limit_hits  INTEGER
──────────────────────────          step_failures_json JSONB
PK  id          BIGSERIAL           recorded_at      TIMESTAMPTZ
    ip_address  INET
    endpoint    VARCHAR(100)
    rejected_at TIMESTAMPTZ
    window_count INTEGER
    window_seconds INTEGER
```

---

## 6. SQL DDL — Complete

```sql
-- ============================================================
-- EXTENSIONS
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- ============================================================
-- FUNCTIONS
-- ============================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- TABLES
-- ============================================================

CREATE TABLE analysis_runs (
    id                  BIGSERIAL       PRIMARY KEY,
    run_id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    ticker              VARCHAR(12)     NOT NULL,
    status              VARCHAR(20)     NOT NULL DEFAULT 'accepted',
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    duration_ms         INTEGER,
    llm_provider        VARCHAR(20)     NOT NULL DEFAULT 'ollama',
    llm_model           VARCHAR(80),
    ip_address          INET,
    report_data         JSONB,
    error_message       TEXT,
    steps_total         SMALLINT        NOT NULL DEFAULT 9,
    steps_completed     SMALLINT        NOT NULL DEFAULT 0,
    steps_failed        SMALLINT        NOT NULL DEFAULT 0,
    is_deleted          BOOLEAN         NOT NULL DEFAULT FALSE,
    deleted_at          TIMESTAMPTZ,
    CONSTRAINT analysis_runs_run_id_unique       UNIQUE (run_id),
    CONSTRAINT analysis_runs_status_check        CHECK (status IN (
        'accepted', 'in_progress', 'complete', 'failed', 'timed_out')),
    CONSTRAINT analysis_runs_llm_provider_check  CHECK (llm_provider IN (
        'ollama', 'openai')),
    CONSTRAINT analysis_runs_steps_completed_range CHECK (
        steps_completed >= 0 AND steps_completed <= steps_total),
    CONSTRAINT analysis_runs_steps_failed_range  CHECK (
        steps_failed >= 0 AND steps_failed <= steps_total),
    CONSTRAINT analysis_runs_duration_positive   CHECK (
        duration_ms IS NULL OR duration_ms >= 0),
    CONSTRAINT analysis_runs_ticker_format       CHECK (
        ticker ~ '^[A-Z]{1,5}(\.[A-Z]{1,3})?$')
);

CREATE TRIGGER trg_analysis_runs_updated_at
    BEFORE UPDATE ON analysis_runs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE pipeline_steps (
    id                  BIGSERIAL       PRIMARY KEY,
    run_id              UUID            NOT NULL,
    step_index          SMALLINT        NOT NULL,
    step_name           VARCHAR(60)     NOT NULL,
    status              VARCHAR(20)     NOT NULL DEFAULT 'pending',
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    duration_ms         INTEGER,
    input_summary       JSONB,
    output_summary      JSONB,
    error_message       TEXT,
    error_code          VARCHAR(60),
    retry_count         SMALLINT        NOT NULL DEFAULT 0,
    CONSTRAINT pipeline_steps_run_fk              FOREIGN KEY (run_id)
        REFERENCES analysis_runs (run_id) ON DELETE CASCADE,
    CONSTRAINT pipeline_steps_unique_step_per_run UNIQUE (run_id, step_index),
    CONSTRAINT pipeline_steps_status_check        CHECK (status IN (
        'pending', 'in_progress', 'complete', 'failed', 'skipped')),
    CONSTRAINT pipeline_steps_step_index_range    CHECK (
        step_index BETWEEN 1 AND 9),
    CONSTRAINT pipeline_steps_duration_positive   CHECK (
        duration_ms IS NULL OR duration_ms >= 0)
);

CREATE TABLE system_metrics_hourly (
    id                      BIGSERIAL       PRIMARY KEY,
    bucket_start            TIMESTAMPTZ     NOT NULL,
    bucket_end              TIMESTAMPTZ     NOT NULL,
    runs_total              INTEGER         NOT NULL DEFAULT 0,
    runs_complete           INTEGER         NOT NULL DEFAULT 0,
    runs_failed             INTEGER         NOT NULL DEFAULT 0,
    runs_timed_out          INTEGER         NOT NULL DEFAULT 0,
    p50_duration_ms         INTEGER,
    p95_duration_ms         INTEGER,
    p99_duration_ms         INTEGER,
    unique_tickers          INTEGER         NOT NULL DEFAULT 0,
    avg_articles_per_run    NUMERIC(6,2),
    rate_limit_hits         INTEGER         NOT NULL DEFAULT 0,
    step_failures_json      JSONB,
    recorded_at             TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT system_metrics_hourly_bucket_unique  UNIQUE (bucket_start),
    CONSTRAINT system_metrics_hourly_bucket_order   CHECK (bucket_end > bucket_start),
    CONSTRAINT system_metrics_hourly_runs_non_neg   CHECK (
        runs_total >= 0 AND runs_complete >= 0 AND
        runs_failed >= 0 AND runs_timed_out >= 0)
);

CREATE TABLE ticker_resolution_cache (
    id                  BIGSERIAL       PRIMARY KEY,
    ticker              VARCHAR(12)     NOT NULL,
    company_name        VARCHAR(200),
    exchange            VARCHAR(20),
    sector              VARCHAR(100),
    industry            VARCHAR(100),
    currency            VARCHAR(10),
    country             VARCHAR(60),
    is_resolvable       BOOLEAN         NOT NULL DEFAULT TRUE,
    resolved_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     NOT NULL,
    CONSTRAINT ticker_resolution_cache_ticker_unique  UNIQUE (ticker),
    CONSTRAINT ticker_resolution_cache_ticker_format  CHECK (
        ticker ~ '^[A-Z]{1,12}(\.[A-Z]{1,3})?$'),
    CONSTRAINT ticker_resolution_cache_expires_after  CHECK (
        expires_at > resolved_at)
);

CREATE TABLE rate_limit_log (
    id                  BIGSERIAL       PRIMARY KEY,
    ip_address          INET            NOT NULL,
    endpoint            VARCHAR(100)    NOT NULL,
    rejected_at         TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    window_count        INTEGER,
    window_seconds      INTEGER
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE UNIQUE INDEX idx_analysis_runs_run_id
    ON analysis_runs (run_id);

CREATE INDEX idx_analysis_runs_ticker_created
    ON analysis_runs (ticker, created_at DESC)
    WHERE is_deleted = FALSE;

CREATE INDEX idx_analysis_runs_created_status
    ON analysis_runs (created_at, status)
    WHERE is_deleted = FALSE;

CREATE INDEX idx_analysis_runs_in_progress
    ON analysis_runs (created_at)
    WHERE status IN ('accepted', 'in_progress') AND is_deleted = FALSE;

CREATE INDEX idx_pipeline_steps_run_id
    ON pipeline_steps (run_id);

CREATE INDEX idx_pipeline_steps_step_name_status
    ON pipeline_steps (step_name, status)
    WHERE status = 'failed';

CREATE INDEX idx_system_metrics_hourly_bucket
    ON system_metrics_hourly (bucket_start DESC);

CREATE INDEX idx_ticker_resolution_cache_expires
    ON ticker_resolution_cache (expires_at)
    WHERE is_resolvable = TRUE;

CREATE INDEX idx_rate_limit_log_rejected_at
    ON rate_limit_log (rejected_at);

CREATE INDEX idx_rate_limit_log_ip
    ON rate_limit_log (ip_address, rejected_at DESC);
```

---

## 7. `report_data` JSONB Schema

The `analysis_runs.report_data` column stores the full assembled `AnalysisReport`. This is the canonical Pydantic model serialized to JSON. The schema below is the target shape (Pydantic model definitions are the authoritative source of truth):

```json
{
  "run_id": "uuid-string",
  "ticker": "AAPL",
  "generated_at": "2025-03-11T12:34:56Z",
  "pipeline_duration_ms": 32450,
  "llm_provider": "ollama",
  "llm_model": "mistral:7b-instruct",
  "completeness": "complete | partial | minimal",

  "company": {
    "name": "Apple Inc.",
    "exchange": "NASDAQ",
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "currency": "USD",
    "country": "United States"
  },

  "market_data": {
    "available": true,
    "price": 172.50,
    "change_pct": 1.23,
    "change_abs": 2.09,
    "volume": 54321000,
    "market_cap": 2710000000000,
    "pe_ratio": 28.4,
    "week_52_high": 199.62,
    "week_52_low": 124.17,
    "data_delayed_minutes": 15,
    "as_of": "2025-03-11T16:00:00Z"
  },

  "price_history": {
    "available": true,
    "period_days": 90,
    "data_points": [
      { "date": "2024-12-11", "close": 168.20 }
    ],
    "trend_direction": "upward | downward | sideways",
    "volatility_flag": false
  },

  "news": {
    "available": true,
    "retrieval_window_days": 30,
    "total_retrieved": 15,
    "total_after_dedup": 11,
    "articles": [
      {
        "article_id": "sha256-hash-of-url",
        "title": "Apple reports record Q1 earnings",
        "source": "Reuters",
        "url": "https://...",
        "published_at": "2025-03-10T09:00:00Z",
        "summary": "Apple exceeded analyst expectations...",
        "topics": ["Earnings", "Revenue"],
        "sentiment": "positive | neutral | negative",
        "sentiment_score": 0.82,
        "content_available": true
      }
    ]
  },

  "sentiment": {
    "available": true,
    "article_count": 11,
    "distribution": {
      "positive": 55,
      "neutral": 27,
      "negative": 18
    },
    "dominant": "Mostly Positive",
    "limited_data_caveat": false,
    "emerging_concern_flag": false
  },

  "events": {
    "available": true,
    "items": [
      {
        "event_type": "Earnings Announcement",
        "description": "Q1 2025 earnings beat estimates by 12%",
        "detected_date": "2025-03-10",
        "source_article_ids": ["sha256-hash-1"]
      }
    ]
  },

  "insights": {
    "available": true,
    "company_overview": "Apple Inc. is a multinational...",
    "recent_developments": "In the most recent 30-day period...",
    "sentiment_overview": "The prevailing sentiment across 11 articles...",
    "potential_drivers": "Strong iPhone cycle upgrade demand...",
    "potential_risks": "Regulatory scrutiny in the EU...",
    "ai_summary": "Apple presents a broadly positive picture...",
    "disclaimer": "This content is AI-generated and does not constitute financial advice."
  },

  "data_sources": [
    {
      "type": "market_data",
      "provider": "Yahoo Finance",
      "data_types": ["price", "volume", "market_cap", "ratios", "ohlcv"]
    },
    {
      "type": "news",
      "provider": "Yahoo Finance RSS",
      "article_count": 15
    }
  ],

  "step_results": [
    {
      "step_index": 1,
      "step_name": "TickerValidator",
      "status": "complete",
      "duration_ms": 820
    }
  ],

  "partial_data_notices": [],
  "error_notices": []
}
```

---

## 8. Critical Queries

### 8.1 Retrieve a run by `run_id` (past-results API)

```sql
SELECT
    run_id,
    ticker,
    status,
    created_at,
    completed_at,
    duration_ms,
    llm_provider,
    llm_model,
    report_data,
    error_message,
    steps_completed,
    steps_failed
FROM analysis_runs
WHERE run_id = $1
  AND is_deleted = FALSE
  AND created_at > NOW() - INTERVAL '24 hours';
```

**Notes:** The TTL filter (`created_at > NOW() - INTERVAL '24 hours'`) is applied at query time, not solely via the cleanup job, to handle the race condition where a run passes the TTL boundary between the hourly cleanup runs. The partial index `idx_analysis_runs_run_id` makes this a sub-millisecond lookup.

---

### 8.2 Insert a new run (analysis request entry)

```sql
INSERT INTO analysis_runs (run_id, ticker, status, ip_address, llm_provider, llm_model)
VALUES ($1, $2, 'accepted', $3, $4, $5)
RETURNING id, run_id, created_at;
```

---

### 8.3 Transition run status (pipeline lifecycle updates)

```sql
-- Mark in_progress (pipeline start)
UPDATE analysis_runs
SET status = 'in_progress',
    started_at = NOW()
WHERE run_id = $1
  AND status = 'accepted';

-- Mark complete (report assembled)
UPDATE analysis_runs
SET status = 'complete',
    completed_at = NOW(),
    duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER * 1000,
    report_data = $2,
    steps_completed = $3,
    steps_failed = $4
WHERE run_id = $1
  AND status = 'in_progress';

-- Mark failed
UPDATE analysis_runs
SET status = 'failed',
    completed_at = NOW(),
    duration_ms = EXTRACT(EPOCH FROM (NOW() - started_at))::INTEGER * 1000,
    error_message = $2,
    steps_completed = $3,
    steps_failed = $4
WHERE run_id = $1
  AND status IN ('accepted', 'in_progress');

-- Mark timed_out (watchdog)
UPDATE analysis_runs
SET status = 'timed_out',
    completed_at = NOW(),
    error_message = 'Pipeline exceeded maximum duration of 90 seconds'
WHERE run_id = $1
  AND status IN ('accepted', 'in_progress');
```

**Concurrency safety note:** The `WHERE status IN (...)` condition on all UPDATE statements provides optimistic locking. If two concurrent updates race (e.g., a watchdog timeout and a natural completion arriving within the same millisecond), only one will match the predicate and succeed. The application checks `rowcount` after each UPDATE; if `rowcount == 0`, the transition is a no-op (the run has already been finalized by another path).

---

### 8.4 Metrics aggregation (hourly job)

```sql
INSERT INTO system_metrics_hourly (
    bucket_start, bucket_end,
    runs_total, runs_complete, runs_failed, runs_timed_out,
    p50_duration_ms, p95_duration_ms, p99_duration_ms,
    unique_tickers, rate_limit_hits, recorded_at
)
SELECT
    DATE_TRUNC('hour', NOW() - INTERVAL '1 hour') AS bucket_start,
    DATE_TRUNC('hour', NOW())                      AS bucket_end,
    COUNT(*)                                       AS runs_total,
    COUNT(*) FILTER (WHERE status = 'complete')    AS runs_complete,
    COUNT(*) FILTER (WHERE status = 'failed')      AS runs_failed,
    COUNT(*) FILTER (WHERE status = 'timed_out')   AS runs_timed_out,
    PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms)
        FILTER (WHERE status = 'complete')         AS p50_duration_ms,
    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)
        FILTER (WHERE status = 'complete')         AS p95_duration_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms)
        FILTER (WHERE status = 'complete')         AS p99_duration_ms,
    COUNT(DISTINCT ticker)                         AS unique_tickers,
    0                                              AS rate_limit_hits,
    -- rate_limit_hits comes from rate_limit_log table separately
    NOW()                                          AS recorded_at
FROM analysis_runs
WHERE created_at >= DATE_TRUNC('hour', NOW() - INTERVAL '1 hour')
  AND created_at <  DATE_TRUNC('hour', NOW())
ON CONFLICT (bucket_start) DO UPDATE SET
    runs_total      = EXCLUDED.runs_total,
    runs_complete   = EXCLUDED.runs_complete,
    runs_failed     = EXCLUDED.runs_failed,
    runs_timed_out  = EXCLUDED.runs_timed_out,
    p50_duration_ms = EXCLUDED.p50_duration_ms,
    p95_duration_ms = EXCLUDED.p95_duration_ms,
    p99_duration_ms = EXCLUDED.p99_duration_ms,
    unique_tickers  = EXCLUDED.unique_tickers,
    recorded_at     = EXCLUDED.recorded_at;
```

---

### 8.5 TTL cleanup job

```sql
-- Step 1: Soft delete expired runs
UPDATE analysis_runs
SET is_deleted = TRUE,
    deleted_at = NOW()
WHERE created_at < NOW() - INTERVAL '24 hours'
  AND is_deleted = FALSE;

-- Step 2: Hard delete runs soft-deleted > 1 hour ago
-- (CASCADE deletes related pipeline_steps rows)
DELETE FROM analysis_runs
WHERE is_deleted = TRUE
  AND deleted_at < NOW() - INTERVAL '1 hour';

-- Step 3: Delete expired ticker resolution cache entries
DELETE FROM ticker_resolution_cache
WHERE expires_at < NOW();

-- Step 4: Delete old rate limit log entries
DELETE FROM rate_limit_log
WHERE rejected_at < NOW() - INTERVAL '7 days';
```

---

## 9. Migration Strategy

### Tooling: Alembic

`alembic` with `asyncpg` dialect is used for all schema migrations. The project uses the `async` migration runner pattern.

**Directory structure:**

```
db/
  alembic.ini
  env.py          ← async engine configuration
  versions/
    0001_initial_schema.py
    0002_add_ticker_resolution_cache.py
    ...
```

**`env.py` async configuration:**

```python
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import settings

def run_migrations_online():
    connectable = create_async_engine(settings.database_url)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
```

**Migration rules:**

1. Every migration is reversible (`upgrade()` and `downgrade()` both implemented).
2. No migration drops a column without first verifying it is unused (two-migration pattern: first migration adds nullable new column; application is deployed; second migration drops old column).
3. Migrations that add indexes use `CREATE INDEX CONCURRENTLY` to avoid table locks in production. `alembic` does not support `CONCURRENTLY` natively; these are wrapped in `op.execute()` with `connection.execution_options(isolation_level="AUTOCOMMIT")`.
4. Migration files are named with zero-padded sequence prefix and snake_case description: `0001_initial_schema.py`, `0003_add_rate_limit_log.py`.

### Versioning Strategy

- Schema version is tracked in the `alembic_version` table (managed by Alembic automatically).
- Application startup includes a migration check: `alembic current` is compared to `alembic head`. If behind, migrations run automatically on startup via `alembic upgrade head`. This is appropriate for MVP/single-server deployment.
- For multi-server deployments (future): migration is decoupled from application startup; a dedicated migration container runs `alembic upgrade head` before new application containers start.

---

## 10. Audit Trail Model

The audit trail for analysis runs is maintained through:

1. **Immutable creation record:** `analysis_runs.created_at` is set once on insert with `DEFAULT NOW()` and is never updated.
2. **Status transition log:** `started_at`, `completed_at`, `updated_at` (trigger-maintained), and `deleted_at` provide a timeline of state changes.
3. **Step-level record:** `pipeline_steps` rows capture the start and end of each step with durations and error codes.
4. **Rate limit log:** `rate_limit_log` provides an append-only record of all rate-limit rejections.

**What the audit trail can answer:**

- When was this run created? (`created_at`)
- How long did the pipeline take? (`duration_ms`)
- Which step failed? (`pipeline_steps WHERE status = 'failed'`)
- Was this run soft-deleted or hard-deleted? (`is_deleted`, `deleted_at`)
- How many requests came from this IP? (`rate_limit_log WHERE ip_address = $1`)

**What the audit trail intentionally does NOT capture:**

- User identity (none collected).
- Full request bodies (ticker only is stored).
- LLM prompt/response content (not stored; only structured output is persisted).

---

## 11. Soft Delete Strategy

**Mechanism:** `is_deleted BOOLEAN DEFAULT FALSE` on `analysis_runs`. The `deleted_at TIMESTAMPTZ` records when soft deletion occurred.

**Policy:**

- All read queries include `WHERE is_deleted = FALSE`.
- The TTL cleanup job sets `is_deleted = TRUE` for runs older than 24 hours.
- Hard DELETE runs 1 hour after soft delete, giving a forensic inspection window.
- `pipeline_steps` rows are hard-deleted via `ON DELETE CASCADE` when the parent `analysis_runs` row is hard-deleted. No separate soft-delete is needed on `pipeline_steps`.

**Reason for soft delete over immediate hard delete:**

- A run could be in the 24–25 hour window where a user has the `run_id` and makes a request that arrives just as the cleanup job runs. With soft delete, the row exists for 1 additional hour, giving the cleanup job's next cycle a chance to confirm deletion rather than creating a race condition.
- Forensic value: if a pipeline failure is reported by a user, the soft-deleted run's `pipeline_steps` rows are still inspectable for up to 1 hour after the 24-hour TTL.

---

## 12. Integrity Invariant List

The following invariants must hold at all times. Violations indicate a programming error, not a user error.

| # | Invariant | Enforcement |
|---|---|---|
| 1 | `analysis_runs.run_id` is globally unique | UNIQUE constraint + partial index |
| 2 | `analysis_runs.ticker` matches `^[A-Z]{1,5}(\.[A-Z]{1,3})?$` | CHECK constraint |
| 3 | `analysis_runs.status` is one of the five defined values | CHECK constraint |
| 4 | `analysis_runs.steps_completed + steps_failed ≤ steps_total` | Application-layer assertion before each UPDATE |
| 5 | A `pipeline_steps` row with `status = 'complete'` has a non-null `completed_at` | Application-layer assertion in step result handler |
| 6 | `pipeline_steps.step_index` is unique per `run_id` | UNIQUE constraint |
| 7 | `analysis_runs.report_data` is non-null only when `status = 'complete'` | Application-layer assertion in ReportAssembler |
| 8 | `ticker_resolution_cache.expires_at > resolved_at` | CHECK constraint |
| 9 | `system_metrics_hourly.bucket_end > bucket_start` | CHECK constraint |
| 10 | An `analysis_runs` row with `is_deleted = TRUE` has a non-null `deleted_at` | Application-layer assertion in cleanup job |
| 11 | No `llm_provider = 'openai'` with a null/empty `llm_model` | Application-layer assertion in AnalyzeRouter |
| 12 | `analysis_runs.duration_ms` is null while `status IN ('accepted', 'in_progress')` | Application-layer: duration is set only on terminal state transition |
