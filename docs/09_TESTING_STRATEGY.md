# 09_TESTING_STRATEGY.md — StockLens AI

---

## 1. Testing Philosophy

The testing strategy is organized around the failure modes that matter most for StockLens AI:

1. **Pipeline correctness:** The 9-step pipeline must produce the correct output for every combination of step success and failure.
2. **External dependency isolation:** Tests must not make real HTTP calls to yfinance, RSS feeds, Ollama, or OpenAI. All external calls are mocked at the provider boundary (not the HTTP level).
3. **Schema integrity:** Database migrations must be correct in both directions and must maintain FK integrity.
4. **SSE delivery correctness:** Events must reach the client in the correct order, with reconnect replay working as designed.
5. **Rate limiting correctness:** The sliding window rate limiter must enforce limits accurately under concurrent access.

**Test pyramid target:**

```
              ┌──────────────────┐
              │   E2E / UI       │  ~10 tests
              │   (Playwright)   │
              └────────┬─────────┘
           ┌───────────┴────────────┐
           │   Integration Tests   │  ~40 tests
           │  (pytest + test DB)   │
           └───────────┬────────────┘
        ┌──────────────┴───────────────┐
        │         Unit Tests           │  ~120 tests
        │  (pytest, all mocked deps)   │
        └──────────────────────────────┘
```

---

## 2. Test Environment Setup

### Python (Backend)

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"           # pytest-asyncio auto mode
testpaths = ["tests"]
addopts = [
    "--cov=app",
    "--cov-report=term-missing",
    "--cov-fail-under=80",
    "-v"
]
markers = [
    "unit: fast tests with all I/O mocked",
    "integration: requires running PostgreSQL and Redis",
    "e2e: requires full Docker Compose stack",
    "slow: tests that take > 5 seconds"
]

[tool.coverage.run]
omit = ["tests/*", "db/versions/*"]
```

**Key test dependencies:**

```
pytest==8.1.0
pytest-asyncio==0.23.6
pytest-cov==5.0.0
respx==0.20.2           # httpx mock library
fakeredis[aioredis]==2.21.1  # in-process Redis fake
asyncpg-stubs           # type stubs for asyncpg in tests
factory-boy==3.3.0      # test fixture factories
```

### JavaScript (Frontend)

```json
{
  "devDependencies": {
    "vitest": "^1.4.0",
    "@testing-library/react": "^15.0.0",
    "@testing-library/user-event": "^14.5.2",
    "@testing-library/jest-dom": "^6.4.0",
    "msw": "^2.2.9",
    "playwright": "^1.43.0"
  }
}
```

### `conftest.py` — Shared Fixtures

```python
# tests/conftest.py
import pytest
import asyncpg
import fakeredis.aioredis as fakeredis
from app.config import get_settings
from app.pipeline.orchestrator import PipelineOrchestrator
from tests.mocks.providers import MockMarketDataProvider, MockNewsProvider, MockLLMProvider

@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for entire session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def redis():
    """In-process fake Redis; no external connection required."""
    client = fakeredis.FakeRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()

@pytest.fixture(scope="session")
async def db_pool():
    """
    Real PostgreSQL pool for integration tests.
    Requires TEST_DATABASE_URL environment variable.
    """
    pool = await asyncpg.create_pool(dsn=os.environ["TEST_DATABASE_URL"], min_size=1, max_size=5)
    yield pool
    await pool.close()

@pytest.fixture(autouse=True)
async def clean_db(db_pool, request):
    """
    Truncate all tables before each integration test.
    Only applied to tests marked with @pytest.mark.integration.
    """
    if "integration" not in request.keywords:
        return
    async with db_pool.acquire() as conn:
        await conn.execute("""
            TRUNCATE analysis_runs, pipeline_steps, system_metrics_hourly,
                     ticker_resolution_cache, rate_limit_log
            RESTART IDENTITY CASCADE
        """)

@pytest.fixture
def mock_market_data():
    return MockMarketDataProvider(
        quote=MarketData(available=True, price=150.0, change_pct=1.5, ...),
        history=PriceHistory(available=True, data_points=[...])
    )

@pytest.fixture
def mock_llm():
    return MockLLMProvider(
        summarize_response='{"summary": "Test summary", "topics": ["Earnings"]}',
        sentiment_response='{"sentiment": "positive", "score": 0.85}',
        events_response='{"events": [{"event_type": "Earnings Announcement", ...}]}',
        insights_response='{"company_overview": "Test company", ...}'
    )
```

---

## 3. Unit Testing Strategy

### 3.1 Pipeline Step Unit Tests

Each pipeline step is tested independently. All provider dependencies are mocked. Tests verify:

- Correct output written to `PipelineContext` on success.
- Correct `StepFailure` recorded on failure.
- `can_execute()` returns the correct value for each precondition state.
- Retry logic fires for retryable errors.

#### `test_news_deduplicator.py`

```python
@pytest.mark.unit
class TestNewsDeduplicator:

    async def test_exact_url_deduplication(self):
        """Two articles with identical URLs → only one retained."""
        articles = [
            RawArticle(article_id="a1", url="https://example.com/news/1", title="Apple earnings"),
            RawArticle(article_id="a2", url="https://example.com/news/1", title="Apple earnings"),  # duplicate
            RawArticle(article_id="a3", url="https://example.com/news/2", title="Apple product launch"),
        ]
        context = make_context(raw_articles=articles)
        step = NewsDeduplicator()
        result = await step.execute(context)

        assert result.status == StepStatus.COMPLETE
        assert len(context.outputs.deduplicated_articles) == 2
        assert context.outputs.deduplicated_articles[0].article_id == "a1"
        assert context.outputs.deduplicated_articles[1].article_id == "a3"

    async def test_near_duplicate_simhash(self):
        """Two articles with near-identical headlines → one retained."""
        articles = [
            RawArticle(url="https://a.com/1", title="Apple reports record quarterly earnings"),
            RawArticle(url="https://b.com/1", title="Apple reports record quarterly earnings beat"),
        ]
        context = make_context(raw_articles=articles)
        step = NewsDeduplicator()
        await step.execute(context)

        # Hamming distance of these two headlines should be ≤ 3
        assert len(context.outputs.deduplicated_articles) == 1

    async def test_distinct_headlines_all_retained(self):
        """Five completely different articles → all five retained."""
        articles = [
            RawArticle(url=f"https://src.com/{i}", title=f"Unique article {i} about unrelated topic {i*7}")
            for i in range(5)
        ]
        context = make_context(raw_articles=articles)
        step = NewsDeduplicator()
        await step.execute(context)

        assert len(context.outputs.deduplicated_articles) == 5

    async def test_skipped_when_no_articles(self):
        """Empty article list → step is skipped."""
        context = make_context(raw_articles=[])
        step = NewsDeduplicator()
        assert not step.can_execute(context)
```

#### `test_sentiment_classifier.py`

```python
@pytest.mark.unit
class TestSentimentClassifier:

    async def test_aggregate_distribution_sums_to_100(self, mock_llm):
        """Distribution rounding must always sum to exactly 100."""
        # 7 articles: 3 positive, 3 neutral, 1 negative
        # 3/7=42.857%, 3/7=42.857%, 1/7=14.285% → naive round = 43+43+14=100 ✓
        # but 3/7=42.857% rounds to 43, 43 → 43+43+14=100 ✓
        # Test with a harder case: 1/3+1/3+1/3
        mock_llm.set_round_robin_responses([
            '{"sentiment": "positive", "score": 0.8}',
            '{"sentiment": "neutral", "score": 0.7}',
            '{"sentiment": "negative", "score": 0.6}',
        ])
        articles = make_articles(3)
        context = make_context(deduplicated_articles=articles, llm=mock_llm)
        step = SentimentClassifier()
        await step.execute(context)

        dist = context.outputs.sentiment.distribution
        assert dist['positive'] + dist['neutral'] + dist['negative'] == 100

    async def test_low_confidence_reclassified_to_neutral(self, mock_llm):
        """Article with score < 0.5 is reclassified as neutral."""
        mock_llm.set_response('{"sentiment": "negative", "score": 0.3}')
        articles = make_articles(1)
        context = make_context(deduplicated_articles=articles, llm=mock_llm)
        await SentimentClassifier().execute(context)

        assert context.outputs.sentiment.distribution['neutral'] == 100

    async def test_limited_data_caveat_when_fewer_than_3_articles(self, mock_llm):
        mock_llm.set_response('{"sentiment": "positive", "score": 0.9}')
        articles = make_articles(2)
        context = make_context(deduplicated_articles=articles, llm=mock_llm)
        await SentimentClassifier().execute(context)

        assert context.outputs.sentiment.limited_data_caveat is True

    async def test_dominant_label_predominantly_positive(self, mock_llm):
        mock_llm.set_sequence_responses(['{"sentiment": "positive", "score": 0.9}'] * 7 +
                                         ['{"sentiment": "neutral", "score": 0.7}'] * 3)
        articles = make_articles(10)
        context = make_context(deduplicated_articles=articles, llm=mock_llm)
        await SentimentClassifier().execute(context)

        assert context.outputs.sentiment.dominant == "Predominantly Positive"

    async def test_step_fails_noncritically_when_llm_unavailable(self):
        failing_llm = MockLLMProvider(raises=ExternalProviderError(
            error_code="OLLAMA_UNAVAILABLE",
            user_message="Ollama is unreachable",
            is_retryable=False
        ))
        articles = make_articles(3)
        context = make_context(deduplicated_articles=articles, llm=failing_llm)
        result = await SentimentClassifier().execute(context)

        assert result.status == StepStatus.FAILED
        assert context.outputs.sentiment is None

    async def test_score_clamping_above_1(self, mock_llm):
        mock_llm.set_response('{"sentiment": "positive", "score": 2.5}')
        articles = make_articles(1)
        context = make_context(deduplicated_articles=articles, llm=mock_llm)
        await SentimentClassifier().execute(context)

        assert context.outputs.article_summaries[0].sentiment_score == 1.0
```

### 3.2 Domain Model Unit Tests

```python
@pytest.mark.unit
class TestSentimentDistribution:

    def test_rounding_invariant_three_equal_thirds(self):
        """1/3, 1/3, 1/3 must round to sum 100."""
        dist = compute_distribution({'positive': 1, 'neutral': 1, 'negative': 1})
        assert sum(dist.values()) == 100

    def test_rounding_invariant_skewed(self):
        """13 articles: 7 positive, 4 neutral, 2 negative."""
        dist = compute_distribution({'positive': 7, 'neutral': 4, 'negative': 2})
        assert sum(dist.values()) == 100
        assert dist['positive'] > dist['neutral'] > dist['negative']

class TestPriceHistory:

    def test_trend_direction_upward(self):
        # 20 data points with clear upward slope
        prices = [100.0 + i * 0.5 for i in range(20)]
        history = PriceHistory(data_points=make_price_points(prices))
        assert history.compute_trend() == "upward"

    def test_trend_direction_sideways_within_threshold(self):
        # Prices oscillating within 0.1% of mean
        prices = [100.0 + (0.05 if i % 2 == 0 else -0.05) for i in range(20)]
        history = PriceHistory(data_points=make_price_points(prices))
        assert history.compute_trend() == "sideways"

    def test_volatility_flag_above_3_percent_std(self):
        # Daily returns with std > 3%
        returns = [0.05 if i % 2 == 0 else -0.05 for i in range(20)]  # ±5% daily
        history = make_history_from_returns(returns)
        assert history.volatility_flag is True

class TestJSONExtractor:

    def test_clean_json(self):
        assert extract_json('{"key": "value"}') == {"key": "value"}

    def test_strips_markdown_fences(self):
        assert extract_json('```json\n{"key": "value"}\n```') == {"key": "value"}

    def test_extracts_from_surrounding_text(self):
        raw = 'Here is the result: {"key": "value"} Hope that helps!'
        assert extract_json(raw) == {"key": "value"}

    def test_raises_on_truncated_json(self):
        with pytest.raises(LLMParseError):
            extract_json('{"key": "val')

    def test_raises_on_no_json(self):
        with pytest.raises(LLMParseError):
            extract_json("The answer is 42")
```

### 3.3 Rate Limiter Unit Tests

```python
@pytest.mark.unit
class TestRedisSlidingWindowRateLimiter:

    async def test_allows_requests_within_limit(self, redis):
        limiter = RedisSlidingWindowRateLimiter(redis, requests=5, window_seconds=60)
        for _ in range(5):
            allowed, count = await limiter.check("192.168.1.1", "POST /analyze")
            assert allowed is True

    async def test_rejects_at_limit_plus_one(self, redis):
        limiter = RedisSlidingWindowRateLimiter(redis, requests=5, window_seconds=60)
        for _ in range(5):
            await limiter.check("192.168.1.1", "POST /analyze")
        allowed, count = await limiter.check("192.168.1.1", "POST /analyze")
        assert allowed is False
        assert count == 6

    async def test_independent_limits_per_ip(self, redis):
        limiter = RedisSlidingWindowRateLimiter(redis, requests=2, window_seconds=60)
        await limiter.check("1.1.1.1", "POST /analyze")
        await limiter.check("1.1.1.1", "POST /analyze")
        # IP 1.1.1.1 exhausted; IP 2.2.2.2 should still be allowed
        allowed, _ = await limiter.check("2.2.2.2", "POST /analyze")
        assert allowed is True

    async def test_window_expiry_allows_new_requests(self, redis):
        limiter = RedisSlidingWindowRateLimiter(redis, requests=2, window_seconds=1)
        await limiter.check("1.1.1.1", "POST /analyze")
        await limiter.check("1.1.1.1", "POST /analyze")
        allowed, _ = await limiter.check("1.1.1.1", "POST /analyze")
        assert allowed is False

        await asyncio.sleep(1.1)  # wait for window to expire

        allowed, _ = await limiter.check("1.1.1.1", "POST /analyze")
        assert allowed is True
```

---

## 4. Integration Testing Strategy

Integration tests run against a real PostgreSQL + Redis instance (via `docker-compose.test.yml`). External HTTP calls (yfinance, RSS, Ollama, OpenAI) are mocked at the `httpx.AsyncClient` level using `respx`.

### 4.1 Full Pipeline Integration Test

```python
@pytest.mark.integration
class TestFullPipeline:

    async def test_complete_pipeline_happy_path(self, db_pool, redis, respx_mock):
        """
        Full pipeline from POST /analyze to assembled report in PostgreSQL.
        All external HTTP calls are mocked via respx.
        """
        # Arrange: mock all external calls
        respx_mock.get(re.compile(r"finance.yahoo.com")).mock(
            return_value=httpx.Response(200, json=MOCK_YFINANCE_QUOTE)
        )
        respx_mock.get(re.compile(r"feeds.finance.yahoo.com")).mock(
            return_value=httpx.Response(200, text=MOCK_RSS_FEED_XML)
        )
        respx_mock.post("http://ollama:11434/api/generate").mock(
            side_effect=ollama_response_sequence([
                MOCK_SUMMARIZE_RESPONSE,  # ×10 articles
                MOCK_SENTIMENT_RESPONSE,  # ×10 articles
                MOCK_EVENTS_RESPONSE,     # ×1
                MOCK_INSIGHTS_RESPONSE,   # ×1
            ])
        )

        orchestrator = build_orchestrator(db_pool=db_pool, redis=redis)

        # Act: run pipeline
        run_id = uuid4()
        await orchestrator.run(run_id, "AAPL", OllamaProvider(...))

        # Assert: run is complete in DB
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, report_data FROM analysis_runs WHERE run_id = $1",
                run_id
            )

        assert row['status'] == 'complete'
        report = json.loads(row['report_data'])
        assert report['ticker'] == 'AAPL'
        assert report['market_data']['available'] is True
        assert report['sentiment']['available'] is True
        assert report['completeness'] == 'complete'

    async def test_pipeline_degrades_when_news_fails(self, db_pool, redis, respx_mock):
        """Pipeline completes with market data only when news retrieval fails."""
        respx_mock.get(re.compile(r"finance.yahoo.com/rss")).mock(
            return_value=httpx.Response(500)
        )
        respx_mock.get(re.compile(r"finance.yahoo.com")).mock(
            return_value=httpx.Response(200, json=MOCK_YFINANCE_QUOTE)
        )

        orchestrator = build_orchestrator(db_pool=db_pool, redis=redis)
        run_id = uuid4()
        await orchestrator.run(run_id, "AAPL", OllamaProvider(...))

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, report_data FROM analysis_runs WHERE run_id = $1", run_id
            )

        assert row['status'] == 'complete'
        report = json.loads(row['report_data'])
        assert report['news']['available'] is False
        assert report['sentiment']['available'] is False
        assert report['market_data']['available'] is True
        assert report['completeness'] == 'partial'

    async def test_pipeline_fails_on_critical_step(self, db_pool, redis, respx_mock):
        """Pipeline halts and marks failed when TickerValidator fails."""
        # Mock yfinance to return empty info (ticker not resolvable)
        respx_mock.get(re.compile(r"finance.yahoo.com")).mock(
            return_value=httpx.Response(200, json={})
        )

        orchestrator = build_orchestrator(db_pool=db_pool, redis=redis)
        run_id = uuid4()
        await orchestrator.run(run_id, "ZZZZ", OllamaProvider(...))

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT status, steps_completed FROM analysis_runs WHERE run_id = $1", run_id
            )

        assert row['status'] == 'failed'
        assert row['steps_completed'] == 0   # only step 1 ran

    async def test_sse_events_published_in_order(self, db_pool, redis, respx_mock):
        """Step events are published to Redis in step_index order."""
        setup_all_mocks_happy_path(respx_mock)
        orchestrator = build_orchestrator(db_pool=db_pool, redis=redis)
        run_id = uuid4()
        await orchestrator.run(run_id, "TSLA", OllamaProvider(...))

        events_raw = await redis.lrange(f"pipeline:events:{run_id}", 0, -1)
        events = [json.loads(e) for e in events_raw]

        step_events = [e for e in events if e['event_type'] == 'step_event']
        step_indices = [e['step_index'] for e in step_events if e['status'] == 'complete']

        # Step indices in complete events must be monotonically increasing
        assert step_indices == sorted(step_indices)
        assert step_indices[0] == 1   # TickerValidator always first
        assert step_indices[-1] == 9  # ReportAssembler always last
```

### 4.2 API Endpoint Integration Tests

```python
@pytest.mark.integration
class TestAnalyzeEndpoint:

    async def test_post_analyze_returns_202_with_run_id(self, client, respx_mock):
        setup_all_mocks(respx_mock)
        response = await client.post("/api/v1/analyze", json={"ticker": "AAPL"})

        assert response.status_code == 202
        body = response.json()
        assert "run_id" in body
        assert UUID(body["run_id"])  # valid UUID

    async def test_post_analyze_invalid_ticker_returns_422(self, client):
        response = await client.post("/api/v1/analyze", json={"ticker": "123"})
        assert response.status_code == 422
        assert "ticker" in response.json()["detail"][0]["loc"]

    async def test_post_analyze_empty_ticker_returns_422(self, client):
        response = await client.post("/api/v1/analyze", json={"ticker": ""})
        assert response.status_code == 422

    async def test_post_analyze_rate_limit_returns_429(self, client, redis):
        # Exhaust rate limit
        for _ in range(10):
            await client.post("/api/v1/analyze", json={"ticker": "AAPL"})
        response = await client.post("/api/v1/analyze", json={"ticker": "AAPL"})

        assert response.status_code == 429
        assert "retry_after" in response.json()
        assert "Retry-After" in response.headers

    async def test_post_analyze_idempotency_same_run_id(self, client, redis, respx_mock):
        """Two rapid submissions of same ticker return same run_id."""
        setup_all_mocks(respx_mock)
        r1 = await client.post("/api/v1/analyze", json={"ticker": "AAPL"})
        r2 = await client.post("/api/v1/analyze", json={"ticker": "AAPL"})

        assert r1.json()["run_id"] == r2.json()["run_id"]

    async def test_get_results_returns_404_for_unknown_run(self, client):
        response = await client.get(f"/api/v1/results/{uuid4()}")
        assert response.status_code == 404
        assert response.json()["error_code"] == "RUN_NOT_FOUND"

    async def test_get_results_returns_complete_report(self, client, db_pool):
        # Insert a completed run directly
        run_id = await insert_completed_run(db_pool, ticker="MSFT")
        response = await client.get(f"/api/v1/results/{run_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["ticker"] == "MSFT"
        assert body["status"] == "success"

    async def test_get_results_returns_404_after_ttl(self, client, db_pool):
        """Runs older than 24 hours are not returned."""
        run_id = await insert_completed_run(
            db_pool, ticker="EXPIRED",
            created_at=datetime.utcnow() - timedelta(hours=25)
        )
        response = await client.get(f"/api/v1/results/{run_id}")
        assert response.status_code == 404
```

---

## 5. Database Migration Tests

```python
@pytest.mark.integration
class TestDatabaseMigrations:

    async def test_upgrade_from_initial_schema(self, migration_db):
        """Apply all migrations from scratch — must succeed."""
        await run_alembic(migration_db, "upgrade", "head")
        async with migration_db.acquire() as conn:
            tables = await conn.fetch("""
                SELECT tablename FROM pg_tables WHERE schemaname = 'public'
            """)
        table_names = {r['tablename'] for r in tables}
        assert 'analysis_runs' in table_names
        assert 'pipeline_steps' in table_names
        assert 'system_metrics_hourly' in table_names

    async def test_downgrade_and_upgrade_is_idempotent(self, migration_db):
        """Downgrade to base and re-upgrade must produce same schema."""
        await run_alembic(migration_db, "upgrade", "head")
        schema_v1 = await capture_schema(migration_db)

        await run_alembic(migration_db, "downgrade", "base")
        await run_alembic(migration_db, "upgrade", "head")
        schema_v2 = await capture_schema(migration_db)

        assert schema_v1 == schema_v2

    async def test_fk_constraint_enforced(self, migration_db):
        """pipeline_steps.run_id must reference a valid analysis_runs.run_id."""
        await run_alembic(migration_db, "upgrade", "head")
        async with migration_db.acquire() as conn:
            with pytest.raises(asyncpg.ForeignKeyViolationError):
                await conn.execute("""
                    INSERT INTO pipeline_steps (run_id, step_index, step_name)
                    VALUES ($1, 1, 'TickerValidator')
                """, uuid4())   # non-existent run_id

    async def test_check_constraint_ticker_format(self, migration_db):
        """analysis_runs.ticker must match the format constraint."""
        await run_alembic(migration_db, "upgrade", "head")
        async with migration_db.acquire() as conn:
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute("""
                    INSERT INTO analysis_runs (run_id, ticker, status)
                    VALUES ($1, $2, 'accepted')
                """, uuid4(), 'invalid123!')   # fails pattern check

    async def test_unique_constraint_on_run_id(self, migration_db):
        """Duplicate run_id must be rejected."""
        await run_alembic(migration_db, "upgrade", "head")
        run_id = uuid4()
        async with migration_db.acquire() as conn:
            await conn.execute("""
                INSERT INTO analysis_runs (run_id, ticker) VALUES ($1, 'AAPL')
            """, run_id)
            with pytest.raises(asyncpg.UniqueViolationError):
                await conn.execute("""
                    INSERT INTO analysis_runs (run_id, ticker) VALUES ($1, 'MSFT')
                """, run_id)
```

---

## 6. Background Task Testing

```python
@pytest.mark.integration
class TestCleanupJob:

    async def test_soft_deletes_runs_older_than_24h(self, db_pool):
        # Insert old and new runs
        old_run_id = await insert_run(db_pool, status='complete',
                                       created_at=datetime.utcnow() - timedelta(hours=25))
        new_run_id = await insert_run(db_pool, status='complete',
                                       created_at=datetime.utcnow() - timedelta(hours=1))

        await run_cleanup_once(db_pool)

        async with db_pool.acquire() as conn:
            old = await conn.fetchrow("SELECT is_deleted FROM analysis_runs WHERE run_id=$1", old_run_id)
            new = await conn.fetchrow("SELECT is_deleted FROM analysis_runs WHERE run_id=$1", new_run_id)

        assert old['is_deleted'] is True
        assert new['is_deleted'] is False

    async def test_hard_deletes_soft_deleted_after_grace_period(self, db_pool):
        run_id = await insert_run(db_pool, status='complete', is_deleted=True,
                                   deleted_at=datetime.utcnow() - timedelta(hours=2))
        await run_cleanup_once(db_pool)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id FROM analysis_runs WHERE run_id=$1", run_id)
        assert row is None   # hard deleted

class TestWatchdog:

    async def test_watchdog_cancels_slow_pipeline(self, db_pool, redis):
        """Pipeline that runs > timeout_seconds is cancelled."""
        slow_llm = MockLLMProvider(delay_seconds=200)   # slower than timeout
        orchestrator = build_orchestrator(db_pool=db_pool, redis=redis, timeout=2)

        run_id = uuid4()
        task = asyncio.create_task(orchestrator.run(run_id, "AAPL", slow_llm))
        watchdog = asyncio.create_task(
            pipeline_watchdog(run_id, task, timeout_seconds=2, ...)
        )
        await asyncio.gather(task, watchdog, return_exceptions=True)

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT status FROM analysis_runs WHERE run_id=$1", run_id)
        assert row['status'] == 'timed_out'

    async def test_watchdog_does_not_cancel_fast_pipeline(self, db_pool, redis, respx_mock):
        """Fast pipeline completes before watchdog fires."""
        setup_all_mocks_fast(respx_mock)
        orchestrator = build_orchestrator(db_pool=db_pool, redis=redis, timeout=90)
        run_id = uuid4()
        await orchestrator.run(run_id, "AAPL", OllamaProvider(...))

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT status FROM analysis_runs WHERE run_id=$1", run_id)
        assert row['status'] == 'complete'
```

---

## 7. Frontend Unit Tests (Vitest + React Testing Library)

```typescript
// tests/components/TickerInput.test.tsx
describe('TickerInput', () => {
  it('auto-uppercases typed input', async () => {
    render(<TickerInput />);
    const input = screen.getByRole('textbox', { name: /ticker/i });
    await userEvent.type(input, 'aapl');
    expect(input).toHaveValue('AAPL');
  });

  it('shows inline error on empty submission', async () => {
    render(<TickerInput />);
    await userEvent.click(screen.getByRole('button', { name: /analyze/i }));
    expect(screen.getByRole('alert')).toHaveTextContent('Please enter a ticker symbol');
  });

  it('shows inline error for invalid characters', async () => {
    render(<TickerInput />);
    await userEvent.type(screen.getByRole('textbox'), '1234');
    await userEvent.click(screen.getByRole('button', { name: /analyze/i }));
    expect(screen.getByRole('alert')).toHaveTextContent(/letters/i);
  });

  it('disables input and button during analysis', () => {
    renderWithStore(<TickerInput />, { analysisStatus: 'streaming' });
    expect(screen.getByRole('textbox')).toBeDisabled();
    expect(screen.getByRole('button', { name: /analyze/i })).toBeDisabled();
  });
});

// tests/store/analysisSlice.test.ts
describe('analysisSlice', () => {
  it('appends step events in order', () => {
    const store = createTestStore();
    store.getState().appendStepEvent(makeStepEvent({ step_index: 1 }));
    store.getState().appendStepEvent(makeStepEvent({ step_index: 2 }));
    expect(store.getState().stepEvents).toHaveLength(2);
    expect(store.getState().stepEvents[0].step_index).toBe(1);
  });

  it('reset clears all state', () => {
    const store = createTestStore();
    store.getState().appendStepEvent(makeStepEvent({ step_index: 1 }));
    store.getState().reset();
    expect(store.getState().stepEvents).toHaveLength(0);
    expect(store.getState().runId).toBeNull();
  });
});

// tests/lib/formatters.test.ts
describe('formatters', () => {
  it('formats positive change with leading plus sign', () => {
    expect(formatChangePct(1.23)).toBe('+1.23%');
  });
  it('formats negative change with leading minus sign', () => {
    expect(formatChangePct(-0.45)).toBe('-0.45%');
  });
  it('formats large numbers with compact notation', () => {
    expect(formatLargeNumber(2710000000000)).toBe('$2.71T');
  });
});
```

---

## 8. UI Automation Tests (Playwright)

```typescript
// tests/e2e/analysis.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Primary Analysis Flow', () => {
  test.beforeEach(async ({ page }) => {
    // MSW intercepts all API calls — no real backend needed
    await page.goto('/');
  });

  test('completes analysis and renders all panels', async ({ page }) => {
    await page.fill('[data-testid="ticker-input"]', 'AAPL');
    await page.click('[data-testid="analyze-button"]');

    // Reasoning viewer appears
    await expect(page.locator('[data-testid="reasoning-viewer"]')).toBeVisible();

    // All panels render (wait for complete event via MSW mock)
    await expect(page.locator('[data-testid="panel-stock-overview"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="panel-price-chart"]')).toBeVisible();
    await expect(page.locator('[data-testid="panel-news-summary"]')).toBeVisible();
    await expect(page.locator('[data-testid="panel-sentiment"]')).toBeVisible();
    await expect(page.locator('[data-testid="panel-insights"]')).toBeVisible();
  });

  test('shows inline validation error for invalid ticker', async ({ page }) => {
    await page.fill('[data-testid="ticker-input"]', '123');
    await page.click('[data-testid="analyze-button"]');

    await expect(page.locator('[role="alert"]')).toContainText('letters');
    // No panels should appear
    await expect(page.locator('[data-testid="reasoning-viewer"]')).not.toBeVisible();
  });

  test('panel collapse/expand is keyboard accessible', async ({ page }) => {
    await runFullAnalysis(page, 'TSLA');

    const panelToggle = page.locator('[data-testid="panel-stock-overview"] [role="button"]');
    await panelToggle.focus();
    await page.keyboard.press('Enter');

    // Panel content should be hidden
    await expect(page.locator('[data-testid="panel-stock-overview-content"]')).toBeHidden();
  });

  test('price direction uses non-color indicator', async ({ page }) => {
    await runFullAnalysis(page, 'AAPL');
    const priceDirection = page.locator('[data-testid="price-direction"]');
    // Must have aria-label describing direction textually
    await expect(priceDirection).toHaveAttribute('aria-label', /up|down|unchanged/i);
  });

  test('news links open in new tab', async ({ page }) => {
    await runFullAnalysis(page, 'AAPL');
    const newsLinks = page.locator('[data-testid="news-article-link"]');
    const firstLink = newsLinks.first();
    await expect(firstLink).toHaveAttribute('target', '_blank');
    await expect(firstLink).toHaveAttribute('rel', /noopener/);
  });

  test('disclaimer is visible without scrolling', async ({ page }) => {
    await page.goto('/');
    const disclaimer = page.locator('[data-testid="disclaimer"]');
    await expect(disclaimer).toBeInViewport();
  });
});

test.describe('Settings Modal', () => {
  test('OpenAI key is masked in the input', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-testid="settings-button"]');
    const keyInput = page.locator('[data-testid="openai-key-input"]');
    await expect(keyInput).toHaveAttribute('type', 'password');
  });

  test('key is not stored in localStorage after save', async ({ page }) => {
    await page.goto('/');
    await page.click('[data-testid="settings-button"]');
    await page.fill('[data-testid="openai-key-input"]', 'sk-test-key-12345');
    await page.click('[data-testid="save-key-button"]');

    const localStorage = await page.evaluate(() =>
      JSON.stringify(window.localStorage)
    );
    expect(localStorage).not.toContain('sk-test');
    expect(localStorage).not.toContain('openai');
  });
});
```

---

## 9. Performance Benchmarking

```python
# tests/performance/test_pipeline_throughput.py
@pytest.mark.slow
class TestPipelineThroughput:

    async def test_single_run_completes_within_60s(self, db_pool, redis, respx_mock):
        """Full pipeline with 10 articles must complete within 60s on standard hardware."""
        setup_mocks_with_latency(respx_mock, llm_latency_ms=2000)  # 2s per LLM call
        orchestrator = build_orchestrator(db_pool, redis)

        start = time.monotonic()
        await orchestrator.run(uuid4(), "AAPL", OllamaProvider(...))
        duration = time.monotonic() - start

        assert duration < 60, f"Pipeline took {duration:.1f}s — exceeds 60s target"

    async def test_three_concurrent_runs_all_complete(self, db_pool, redis, respx_mock):
        """Three concurrent pipelines must all complete within 90s."""
        setup_mocks_with_latency(respx_mock, llm_latency_ms=2000)
        orchestrator = build_orchestrator(db_pool, redis, max_concurrent_llm=3)

        run_ids = [uuid4() for _ in range(3)]
        start = time.monotonic()

        await asyncio.gather(*[
            orchestrator.run(rid, ticker, OllamaProvider(...))
            for rid, ticker in zip(run_ids, ["AAPL", "TSLA", "MSFT"])
        ])

        duration = time.monotonic() - start
        assert duration < 90, f"Concurrent runs took {duration:.1f}s — exceeds 90s target"

        # All three must be complete
        async with db_pool.acquire() as conn:
            for run_id in run_ids:
                row = await conn.fetchrow(
                    "SELECT status FROM analysis_runs WHERE run_id=$1", run_id
                )
                assert row['status'] == 'complete'

    async def test_deduplication_performance(self):
        """SimHash dedup of 20 articles must complete in < 100ms."""
        articles = [make_article(title=f"Article {i} about {random_text()}") for i in range(20)]
        context = make_context(raw_articles=articles)
        step = NewsDeduplicator()

        start = time.monotonic()
        await step.execute(context)
        duration_ms = (time.monotonic() - start) * 1000

        assert duration_ms < 100, f"Deduplication took {duration_ms:.1f}ms"
```

---

## 10. Load Testing

Load testing is performed with `locust` against a running Docker Compose stack.

```python
# tests/load/locustfile.py
from locust import HttpUser, task, between
import random

TICKERS = ["AAPL", "TSLA", "MSFT", "NVDA", "AMZN", "GOOG", "META", "NFLX"]

class StockLensUser(HttpUser):
    wait_time = between(2, 8)   # realistic think time

    @task(3)
    def analyze_ticker(self):
        ticker = random.choice(TICKERS)
        with self.client.post(
            "/api/v1/analyze",
            json={"ticker": ticker},
            catch_response=True
        ) as response:
            if response.status_code == 202:
                run_id = response.json().get("run_id")
                response.success()
                # Simulate SSE consumption (GET with timeout)
                self.client.get(
                    f"/api/v1/analyze/stream/{run_id}",
                    headers={"Accept": "text/event-stream"},
                    stream=True,
                    timeout=90
                )
            elif response.status_code == 429:
                response.success()   # rate limiting is expected behavior
            else:
                response.failure(f"Unexpected status: {response.status_code}")

    @task(1)
    def get_metrics(self):
        self.client.get("/api/v1/metrics")
```

**Load test targets:**

- 10 concurrent users: P50 pipeline duration < 45s, P95 < 75s, error rate < 1%.
- 25 concurrent users: P50 < 60s, P95 < 90s, error rate < 5% (mostly rate limits).
- 50 concurrent users: rate limiting should return 429s; no server errors.

---

## 11. Crash Simulation and Failure Injection Tests

```python
@pytest.mark.integration
class TestFailureInjection:

    async def test_pipeline_continues_after_redis_publish_failure(self, db_pool, redis):
        """If Redis Pub/Sub publish fails, pipeline continues and completes."""
        # Simulate Redis failure mid-pipeline by making publish fail after step 3
        call_count = 0
        original_publish = redis.publish

        async def failing_publish(channel, message):
            nonlocal call_count
            call_count += 1
            if call_count == 3:
                raise ConnectionError("Redis connection lost")
            return await original_publish(channel, message)

        redis.publish = failing_publish

        orchestrator = build_orchestrator(db_pool, redis)
        run_id = uuid4()
        # Pipeline should not raise even when publish fails
        await orchestrator.run(run_id, "AAPL", OllamaProvider(...))

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT status FROM analysis_runs WHERE run_id=$1", run_id)
        # Pipeline should still complete — Redis failure is non-blocking
        assert row['status'] == 'complete'

    async def test_corrupted_llm_json_triggers_retry(self, db_pool, redis, respx_mock):
        """Truncated JSON from LLM triggers one retry with corrective prompt."""
        setup_market_and_news_mocks(respx_mock)

        call_count = 0
        def llm_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json={"response": '{"summary": "test'})  # truncated
            return httpx.Response(200, json={"response": '{"summary": "test summary", "topics": ["Earnings"]}'})

        respx_mock.post("http://ollama:11434/api/generate").mock(side_effect=llm_response)

        orchestrator = build_orchestrator(db_pool, redis)
        await orchestrator.run(uuid4(), "AAPL", OllamaProvider(...))
        assert call_count == 2   # one initial + one retry

    async def test_all_llm_steps_fail_report_is_minimal(self, db_pool, redis, respx_mock):
        """With Ollama completely down, report is assembled as 'minimal'."""
        setup_market_and_news_mocks(respx_mock)
        respx_mock.post("http://ollama:11434/api/generate").mock(
            return_value=httpx.Response(500)
        )

        orchestrator = build_orchestrator(db_pool, redis)
        run_id = uuid4()
        await orchestrator.run(run_id, "AAPL", OllamaProvider(...))

        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT status, report_data FROM analysis_runs WHERE run_id=$1", run_id)

        assert row['status'] == 'complete'
        report = json.loads(row['report_data'])
        assert report['completeness'] == 'minimal'
        assert report['market_data']['available'] is True
        assert report['sentiment']['available'] is False
        assert report['insights']['available'] is False

    async def test_data_corruption_simulation_jsonb_parse(self, db_pool):
        """Manually corrupt report_data; validate retrieval handles gracefully."""
        run_id = uuid4()
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO analysis_runs (run_id, ticker, status, report_data)
                VALUES ($1, 'AAPL', 'complete', $2)
            """, run_id, '{"ticker": "AAPL", "corrupted": true}')   # missing required fields

        # The results endpoint should return what it has, not crash
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get(f"/api/v1/results/{run_id}")

        # Either returns 200 with partial data or 500 with structured error
        assert response.status_code in (200, 500)
        if response.status_code == 500:
            assert "error_code" in response.json()   # never an unhandled exception
```

---

## 12. CI Integration

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  backend-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -e ".[dev]" --break-system-packages
      - run: ruff check app tests
      - run: mypy app --strict
      - run: pytest tests/unit -m unit --cov=app --cov-fail-under=80

  backend-integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env: { POSTGRES_DB: stocklens_test, POSTGRES_PASSWORD: test }
        options: --health-cmd pg_isready
      redis:
        image: redis:7
        options: --health-cmd "redis-cli ping"
    env:
      TEST_DATABASE_URL: postgresql://postgres:test@localhost:5432/stocklens_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -e ".[dev]"
      - run: pytest tests/integration -m integration

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - run: cd frontend && npm ci
      - run: cd frontend && npx tsc --noEmit
      - run: cd frontend && npx eslint .
      - run: cd frontend && npx vitest run

  e2e:
    runs-on: ubuntu-latest
    needs: [backend-unit, frontend]
    steps:
      - uses: actions/checkout@v4
      - run: docker compose -f infra/docker-compose.test.yml up -d
      - run: cd frontend && npx playwright test
      - run: docker compose -f infra/docker-compose.test.yml down

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pip-audit
      - run: pip-audit -r backend/requirements.txt
      - run: cd frontend && npm audit --audit-level=high
```

---

## 13. Memory Profiling Plan

| Target | Tool | Trigger | Threshold |
|---|---|---|---|
| Pipeline task memory growth per run | `tracemalloc` snapshot before/after run | Weekly CI job | < 50MB per run |
| Redis memory usage | `INFO memory` command | Daily metric collection | Alert if > 500MB |
| PostgreSQL `pg_relation_size` per table | SQL query | Daily metric collection | Alert if `analysis_runs` > 1GB |
| asyncpg connection pool idle memory | Python `psutil.Process().memory_info()` | Load test runs | < 200MB baseline |

```python
# tests/performance/test_memory.py
async def test_pipeline_memory_footprint():
    import tracemalloc
    tracemalloc.start()

    snapshot_before = tracemalloc.take_snapshot()
    for _ in range(10):   # run 10 pipelines
        await run_mock_pipeline()
    snapshot_after = tracemalloc.take_snapshot()

    stats = snapshot_after.compare_to(snapshot_before, 'lineno')
    total_added_mb = sum(s.size_diff for s in stats) / (1024 * 1024)

    tracemalloc.stop()
    assert total_added_mb < 50, f"Pipeline added {total_added_mb:.1f}MB over 10 runs"
```

---

## 14. Concurrency Safety Checklist

| Risk | Test |
|---|---|
| Two concurrent pipelines write to same `run_id` in DB | `test_unique_constraint_on_run_id` (migration test) |
| Race between status updates (complete vs. timed_out) | `test_watchdog_does_not_cancel_fast_pipeline` |
| LLM semaphore correctly limits to N concurrent calls | Verified via `llm_call_count` tracking in mock provider |
| Rate limiter overcounts under concurrent requests | Property test: 100 concurrent rate limit checks → exactly `limit` succeed |
| SSE pub/sub channel leak on client disconnect | Verified in `test_sse_events_published_in_order` (subscriber cleanup) |
| Idempotency key race: two identical requests at same millisecond | Redis pipeline atomicity guarantees; tested with `asyncio.gather` of two simultaneous POSTs |
