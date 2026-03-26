# 04_DOMAIN_ENGINE_DESIGN.md — StockLens AI

---

## 1. Domain Model Philosophy

The domain layer encodes what the system *does*, independent of how it communicates (HTTP), where it stores data (PostgreSQL), or what external tools it calls (yfinance, Ollama). The domain is the analysis pipeline.

**Core philosophy:**

- **Pipeline as domain primitive.** The 9-step sequential execution graph is the central domain concept. It is not an infrastructure concern, not a service concern — it is the business logic itself.
- **Context as the unit of truth.** A `PipelineContext` object is the single mutable aggregate that flows through all steps. It accumulates outputs and failure records. No step communicates with another step except through this shared context.
- **Explicit failure semantics.** Every step either succeeds and writes to the context, or fails and records a structured `StepFailure` in the context. There is no implicit failure via exception propagation (exceptions are caught by the orchestrator). This makes the partial-report behavior contractually explicit.
- **No anemic domain model.** The domain objects (`AnalysisReport`, `SentimentResult`, `ExtractedEvent`, `ArticleSummary`) carry behavior, not just data. For example, `SentimentResult.dominant_label()` computes the dominant narrative from the distribution; `NewsCollection.deduplicated()` returns a new `NewsCollection` with duplicates removed.
- **Immutable step outputs.** `StepResult` objects returned by each step are frozen Pydantic models. The orchestrator writes them into the mutable `PipelineContext`, but the objects themselves cannot be mutated after creation.

---

## 2. Domain Object Hierarchy

```
PipelineContext                      ← mutable aggregate; owns the run
├── run_id: UUID
├── ticker: str
├── llm_provider: LLMProvider        ← injected; not a data object
├── step_registry: list[PipelineStep]
├── step_states: dict[str, StepState]
│     └── StepState
│           ├── status: StepStatus
│           ├── started_at: datetime
│           ├── completed_at: datetime
│           └── failure: StepFailure | None
├── outputs: PipelineOutputs         ← accumulated results
│     ├── company: CompanyInfo | None
│     ├── market_data: MarketData | None
│     ├── price_history: PriceHistory | None
│     ├── raw_articles: list[RawArticle]
│     ├── deduplicated_articles: list[RawArticle]
│     ├── article_summaries: list[ArticleSummary]
│     ├── sentiment: SentimentResult | None
│     ├── events: list[ExtractedEvent]
│     └── insights: InsightSections | None
└── assembled_report: AnalysisReport | None   ← set by ReportAssembler

AnalysisReport                       ← immutable; persisted to PostgreSQL
├── run_id, ticker, generated_at
├── company: CompanyInfo
├── market_data: MarketData
├── price_history: PriceHistory
├── news: NewsSection
├── sentiment: SentimentSection
├── events: EventsSection
├── insights: InsightSection
├── data_sources: list[DataSource]
├── step_results: list[StepResultSummary]
├── completeness: ReportCompleteness
├── partial_data_notices: list[str]
└── error_notices: list[str]
```

---

## 3. PipelineStep Interface (Protocol)

```python
from typing import Protocol
from dataclasses import dataclass
from enum import Enum

class StepStatus(str, Enum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETE    = "complete"
    FAILED      = "failed"
    SKIPPED     = "skipped"

@dataclass(frozen=True)
class StepFailure:
    error_code: str          # e.g. "EXTERNAL_PROVIDER_TIMEOUT"
    message: str             # human-readable; NOT a traceback
    is_retryable: bool
    retry_count: int = 0

@dataclass(frozen=True)
class StepResult:
    step_name: str
    status: StepStatus
    data: dict               # step-specific output payload
    failure: StepFailure | None = None
    duration_ms: int = 0

class PipelineStep(Protocol):
    name: str
    step_index: int
    critical: bool           # if True, failure halts the pipeline
    max_retries: int         # 0 = no retry; 1 = one retry on retryable failure

    async def execute(self, context: "PipelineContext") -> StepResult:
        ...

    def can_execute(self, context: "PipelineContext") -> bool:
        """
        Returns False if this step's prerequisites are not satisfied.
        e.g. ArticleSummarizer returns False if context.outputs.deduplicated_articles is empty.
        The orchestrator calls this before executing the step; if False, the step is SKIPPED.
        """
        ...
```

---

## 4. PipelineOrchestrator — Core Algorithm

```python
class PipelineOrchestrator:
    def __init__(
        self,
        steps: list[PipelineStep],
        event_bus: EventBus,
        report_repository: ReportRepository,
        llm_semaphore: asyncio.Semaphore
    ):
        self._steps = steps
        self._event_bus = event_bus
        self._report_repository = report_repository
        self._llm_semaphore = llm_semaphore

    async def run(
        self,
        run_id: UUID,
        ticker: str,
        llm_provider: LLMProvider
    ) -> None:
        """
        Executes the full pipeline for a given run_id.
        This coroutine is launched as an asyncio.Task.
        All exceptions are caught internally; no exception propagates to the caller.
        """
        context = PipelineContext(
            run_id=run_id,
            ticker=ticker,
            llm_provider=llm_provider
        )

        # Publish: pipeline accepted → in_progress
        await self._event_bus.publish(run_id, PipelineStartedEvent(run_id=run_id, ticker=ticker))

        pipeline_timed_out = False

        try:
            for step in self._steps:
                # ── Prerequisites check ──────────────────────────────
                if not step.can_execute(context):
                    context.record_skip(step)
                    await self._event_bus.publish(run_id, StepEvent(
                        step_name=step.name,
                        step_index=step.step_index,
                        status=StepStatus.SKIPPED,
                        reason="Prerequisites not met; step skipped"
                    ))
                    continue

                # ── Step execution with retry ────────────────────────
                result = await self._execute_with_retry(step, context, run_id)

                # ── Publish step event ───────────────────────────────
                await self._event_bus.publish(run_id, StepEvent(
                    step_name=step.name,
                    step_index=step.step_index,
                    status=result.status,
                    data=result.data,
                    duration_ms=result.duration_ms,
                    reason=result.failure.message if result.failure else None
                ))

                # ── Write step record to DB ──────────────────────────
                # Fire-and-forget DB write; does not block pipeline
                asyncio.create_task(
                    self._report_repository.upsert_step(run_id, result)
                )

                # ── Critical step failure: halt ──────────────────────
                if result.status == StepStatus.FAILED and step.critical:
                    await self._event_bus.publish(run_id, PipelineFailedEvent(
                        run_id=run_id,
                        reason=result.failure.message,
                        failed_step=step.name
                    ))
                    await self._report_repository.mark_failed(
                        run_id,
                        reason=result.failure.message,
                        steps_completed=context.steps_completed_count,
                        steps_failed=context.steps_failed_count
                    )
                    return

        except asyncio.CancelledError:
            # Watchdog timeout cancelled this task
            pipeline_timed_out = True
            await self._event_bus.publish(run_id, PipelineTimeoutEvent(run_id=run_id))
            await self._report_repository.mark_timed_out(run_id)
            return

        except Exception as e:
            # Unhandled programming error — should never happen in production
            # Log at CRITICAL level; mark run as failed
            logger.critical("Unhandled exception in pipeline", run_id=str(run_id), exc_info=e)
            await self._event_bus.publish(run_id, PipelineFailedEvent(
                run_id=run_id,
                reason="Internal system error"
            ))
            await self._report_repository.mark_failed(run_id, reason="Internal error")
            return

        # ── Assemble and persist report ──────────────────────────────
        report = context.assemble_report()
        try:
            await self._report_repository.save_report(run_id, report)
        except Exception as e:
            logger.error("Failed to persist report", run_id=str(run_id), exc_info=e)
            # Do NOT fail the pipeline for a DB write error; user already received all data via SSE

        await self._event_bus.publish(run_id, PipelineCompleteEvent(
            run_id=run_id,
            completeness=report.completeness
        ))

    async def _execute_with_retry(
        self,
        step: PipelineStep,
        context: PipelineContext,
        run_id: UUID
    ) -> StepResult:
        """
        Executes a step with retry logic for retryable failures.
        Maximum retries are defined per step (step.max_retries).
        Non-retryable failures are returned immediately.
        """
        attempt = 0
        last_result: StepResult | None = None

        while attempt <= step.max_retries:
            attempt += 1
            start_ms = time.monotonic_ns() // 1_000_000

            # ── Publish in_progress event on first attempt ───────────
            if attempt == 1:
                context.record_start(step)
                await self._event_bus.publish(run_id, StepEvent(
                    step_name=step.name,
                    step_index=step.step_index,
                    status=StepStatus.IN_PROGRESS
                ))

            try:
                result = await step.execute(context)
                duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
                final_result = StepResult(
                    step_name=result.step_name,
                    status=result.status,
                    data=result.data,
                    failure=result.failure,
                    duration_ms=duration_ms
                )
                context.record_complete(step, final_result)
                return final_result

            except ExternalProviderError as e:
                duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
                failure = StepFailure(
                    error_code=e.error_code,
                    message=e.user_message,
                    is_retryable=e.is_retryable,
                    retry_count=attempt - 1
                )
                last_result = StepResult(
                    step_name=step.name,
                    status=StepStatus.FAILED,
                    data={},
                    failure=failure,
                    duration_ms=duration_ms
                )
                if not e.is_retryable or attempt > step.max_retries:
                    context.record_failure(step, last_result)
                    return last_result

                # Retryable: wait with exponential backoff before retry
                backoff_seconds = min(2 ** (attempt - 1), 8)  # 1s, 2s, 4s, 8s max
                await asyncio.sleep(backoff_seconds)

            except LLMParseError as e:
                # LLM returned non-parseable output; retry with corrective prompt hint
                duration_ms = (time.monotonic_ns() // 1_000_000) - start_ms
                context.set_llm_retry_hint(step.name)  # step reads this on next attempt
                failure = StepFailure(
                    error_code="LLM_JSON_PARSE_ERROR",
                    message="AI model returned an unexpected response format",
                    is_retryable=(attempt <= step.max_retries),
                    retry_count=attempt - 1
                )
                last_result = StepResult(
                    step_name=step.name,
                    status=StepStatus.FAILED,
                    data={},
                    failure=failure,
                    duration_ms=duration_ms
                )
                if attempt > step.max_retries:
                    context.record_failure(step, last_result)
                    return last_result
                await asyncio.sleep(1)

        context.record_failure(step, last_result)
        return last_result
```

---

## 5. Step Definitions and Business Rules

### Step 1 — TickerValidator

**Critical: YES** | **Max retries: 1**

**Business rules:**

1. Input ticker must match `^[A-Z]{1,5}(\.[A-Z]{1,3})?$` after uppercasing. This is re-validated at the domain layer even though it was validated at the HTTP layer (defense in depth).
2. Check `ticker_resolution_cache` in Redis first (TTL=1h). If hit, use cached result.
3. If cache miss, call `MarketDataProvider.resolve_ticker(ticker)`. This returns `CompanyInfo | None`.
4. If `CompanyInfo` is `None`: the ticker is not resolvable. Store negative cache entry in Redis (TTL=24h to suppress repeated lookups). Write `is_resolvable=FALSE` to `ticker_resolution_cache`. Set `context.outputs.company = None`. Return `FAILED` with `error_code="TICKER_NOT_RESOLVABLE"`.
5. If `CompanyInfo` is returned: write to Redis cache and `ticker_resolution_cache` DB table. Set `context.outputs.company = company_info`. Return `COMPLETE`.

**Pseudocode:**

```
resolve ticker from cache (Redis) → if hit, return COMPLETE
call MarketDataProvider.resolve_ticker(ticker)
  if None:
    write negative cache entry
    return FAILED (critical) → pipeline halts
  else:
    write positive cache entry
    context.outputs.company = company_info
    return COMPLETE
```

**Why critical:** Without a resolved company identity, every downstream step (news retrieval by company name, insight generation referencing company context) is operating blindly. The pipeline must halt.

---

### Step 2 — MarketDataCollector

**Critical: NO** | **Max retries: 1**

**Business rules:**

1. Call `MarketDataProvider.get_quote(ticker)` → `MarketData | None`.
2. Call `MarketDataProvider.get_price_history(ticker, days=90)` → `PriceHistory | None`.
3. Steps 2 and 3 are executed concurrently via `asyncio.gather` in the orchestrator (the orchestrator has an optimization: if steps N and N+1 are both non-critical and have no data dependency on each other, they are gathered). However, for implementation simplicity in MVP, they run sequentially. Parallelism is noted as a Phase 2 optimization.
4. If `MarketData` is `None`: set `context.outputs.market_data = None`. The context records this as `market_data_available = False`.
5. `MarketData.change_direction` is computed from `change_pct`: `"up"` if > 0, `"down"` if < 0, `"flat"` if == 0.
6. `PriceHistory.trend_direction` is computed using the linear regression slope over the last 20 data points:

```
slope = LinearRegression([close_prices[-20:]]).coef_[0]
if slope > threshold_positive:  trend = "upward"
elif slope < threshold_negative: trend = "downward"
else:                            trend = "sideways"
```

where `threshold_positive = 0.005 * mean(prices)` and `threshold_negative = -0.005 * mean(prices)` (0.5% of mean price per day as the threshold for "meaningful" slope).

1. `PriceHistory.volatility_flag` is set to `True` if the standard deviation of daily returns in the period exceeds 3%.

---

### Step 3 — NewsRetriever

**Critical: NO** | **Max retries: 1**

**Business rules:**

1. Build search signals: `ticker` AND `company_name` (from `context.outputs.company`).
2. Fetch from configured RSS feed URLs by substituting the ticker symbol.
3. For each article in the RSS response: parse `title`, `url`, `published_date`, `source`.
4. Filter articles: `published_date` must be within the last `NEWS_WINDOW_DAYS` (default: 30) days. Articles outside this window are discarded.
5. Filter for relevance: article title or description must contain the ticker OR the company name (case-insensitive). This filters out irrelevant articles that appear in a general financial RSS feed.
6. Maximum `MAX_ARTICLES = 20`: if more articles pass filters, sort by `published_date DESC` and take the top 20.
7. If zero articles pass filters: set `context.outputs.raw_articles = []`. This is NOT a step failure — it is a valid business state. Return `COMPLETE` with `article_count=0`.
8. Set `context.outputs.raw_articles = filtered_articles`. Return `COMPLETE`.

**Article ID generation:**

```python
article_id = hashlib.sha256(article.url.encode()).hexdigest()[:16]
```

This deterministic ID is used for deduplication and for linking events to source articles.

---

### Step 4 — NewsDeduplicator

**Critical: NO** | **Max retries: 0** (purely computational; no external calls)

**Business rules:**

1. If `context.outputs.raw_articles` is empty: mark as `SKIPPED`. Return.
2. Deduplication uses a two-pass algorithm:

**Pass 1 — Exact URL deduplication:**
Build a `set` of URLs. Keep only the first occurrence of each URL. Time complexity: O(n).

**Pass 2 — Near-duplicate detection via SimHash:**
For each article headline, compute a 64-bit SimHash fingerprint. Two articles are near-duplicates if their Hamming distance is ≤ 3 bits (out of 64).

```python
def simhash(text: str) -> int:
    """
    64-bit SimHash of normalized headline text.
    """
    tokens = normalize_text(text).split()  # lowercase, remove punctuation
    v = [0] * 64
    for token in tokens:
        h = mmh3.hash64(token)[0]  # MurmurHash3 64-bit
        for i in range(64):
            if h & (1 << i):
                v[i] += 1
            else:
                v[i] -= 1
    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= (1 << i)
    return fingerprint

def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count('1')
```

For each article, compare its SimHash against all previously accepted articles. If Hamming distance ≤ 3 to any accepted article, the article is a duplicate — discard it and increment a `dedup_count` counter.

1. Set `context.outputs.deduplicated_articles = deduplicated`. Record `dedup_count` in output summary.
2. Return `COMPLETE`.

**Edge case — all articles are duplicates:** `deduplicated_articles` will be `[articles[0]]` (the first article is always accepted). The output summary records `dedup_count = n-1`.

---

### Step 5 — ArticleSummarizer

**Critical: NO** | **Max retries: 1 (per article)**

**Business rules:**

1. If `deduplicated_articles` is empty: `SKIPPED`.
2. For each article: acquire `llm_semaphore`, then call `LLMProvider.summarize(article)`.
3. Articles are processed in batches of 3 (controlled by `asyncio.gather` with `asyncio.Semaphore(3)`):

```python
semaphore = asyncio.Semaphore(3)

async def summarize_one(article: RawArticle) -> ArticleSummary:
    async with semaphore:
        return await llm_provider.summarize(article, retry_hint=context.get_llm_retry_hint("ArticleSummarizer"))

summaries = await asyncio.gather(
    *[summarize_one(a) for a in context.outputs.deduplicated_articles],
    return_exceptions=True
)
```

1. For each result: if `Exception`, that article gets a partial `ArticleSummary` with `summary=None` and `summarization_failed=True`. The article is still included in the report with its headline.
2. **Prompt template (Jinja2):**

```
You are a financial news analyst. Summarize the following article headline in 1-2 sentences.
Also extract the key topics from: Earnings, Acquisitions, Regulatory, Product Launch, Leadership Change, Market Movement, Other.

Article headline: {{ title }}
{% if content %}Article content (first 500 characters): {{ content[:500] }}{% endif %}

Respond ONLY with valid JSON in this exact format:
{
  "summary": "string",
  "topics": ["topic1", "topic2"]
}
```

1. `ArticleSummary.topics` is constrained to the defined taxonomy. The LLM output parser validates topics against the allowed set; unrecognized topics are replaced with `"Other"`.
2. Set `context.outputs.article_summaries`. Return `COMPLETE` even if some individual articles failed summarization (partial failure).

---

### Step 6 — SentimentClassifier

**Critical: NO** | **Max retries: 1**

**Business rules:**

1. If `deduplicated_articles` is empty: `SKIPPED`. Sentiment section will be unavailable.
2. Process articles in the same batched-parallel pattern as Step 5.
3. **Prompt template:**

```
Classify the sentiment of the following financial news headline as one of: positive, neutral, negative.
Return a confidence score between 0.0 and 1.0.

Headline: {{ title }}
{% if summary %}Summary: {{ summary }}{% endif %}

Respond ONLY with valid JSON:
{
  "sentiment": "positive|neutral|negative",
  "score": 0.0
}
```

1. Score validation: `score` must be in `[0.0, 1.0]`. If the LLM returns a value outside this range, clamp it.
2. Aggregate distribution:

```python
counts = Counter(a.sentiment for a in sentiment_results)
total = len(sentiment_results)
distribution = {
    "positive": round(counts["positive"] / total * 100),
    "neutral": round(counts["neutral"] / total * 100),
    "negative": round(counts["negative"] / total * 100),
}
# Fix rounding to sum to exactly 100:
diff = 100 - sum(distribution.values())
# Apply diff to the category with the largest remainder
largest_category = max(distribution, key=lambda k: (counts[k] / total * 100) % 1)
distribution[largest_category] += diff
```

1. Dominant label derivation:

| Condition | Label |
|---|---|
| positive ≥ 60% | "Predominantly Positive" |
| positive ≥ 40% AND negative < 25% | "Mostly Positive" |
| negative ≥ 60% | "Predominantly Negative" |
| negative ≥ 40% AND positive < 25% | "Mostly Negative" |
| abs(positive - negative) ≤ 15 AND neutral > 40% | "Neutral / No Strong Signal" |
| default | "Mixed" |

1. Emerging concern detection: if `negative > 50%` AND the analysis is for a ticker that previously had < 30% negative (from recent cached metrics — **Phase 2**; MVP: skip this check). For MVP: `emerging_concern_flag = False` unless `negative ≥ 70%`.

2. `limited_data_caveat`: set to `True` if `total < 3`.
3. `context.outputs.sentiment = SentimentResult(...)`. Return `COMPLETE`.

---

### Step 7 — EventExtractor

**Critical: NO** | **Max retries: 1**

**Business rules:**

1. If `deduplicated_articles` is empty: `SKIPPED`.
2. Unlike summarization (per-article), event extraction operates on the full corpus with a single LLM call. This avoids per-article LLM overhead for event detection and produces better cross-article event deduplication.
3. Input to the prompt: concatenated `title + summary` for all articles (up to `MAX_ARTICLES=20`).
4. **Prompt template:**

```
You are a financial analyst. From the following news articles about {{ company_name }} ({{ ticker }}),
identify significant business events. Only include events that are clearly supported by the articles.

Event types to detect:
- Earnings Announcement
- Acquisition or Merger
- Regulatory Action
- Product Launch
- Leadership Change
- Other Significant Event

Articles:
{% for article in articles %}
[{{ loop.index }}] {{ article.title }}{% if article.summary %} — {{ article.summary }}{% endif %}
{% endfor %}

Respond ONLY with valid JSON:
{
  "events": [
    {
      "event_type": "string",
      "description": "string (one sentence)",
      "detected_date": "YYYY-MM-DD or null",
      "source_article_indices": [1, 2]
    }
  ]
}
```

1. Post-processing:
   - `event_type` is validated against the allowed taxonomy. Unrecognized types → `"Other Significant Event"`.
   - `source_article_indices` are converted to `source_article_ids` using the ordered article list.
   - `detected_date` is validated as an ISO date string. If the LLM provides an invalid date, it is set to `None`.
   - Events with empty `description` are discarded.
   - Maximum 10 events are retained (sorted by source article recency).

2. Same event from multiple articles: the LLM is expected to deduplicate naturally in its response. If identical `description` strings are detected in the output, keep only the first and merge `source_article_indices`.

---

### Step 8 — InsightGenerator

**Critical: NO** | **Max retries: 1**

**Business rules:**

1. This step synthesizes all available context. It runs regardless of whether all prior steps succeeded, using only the data that is available.
2. The orchestrator passes a `InsightGeneratorInput` (derived from `context.outputs`) that explicitly marks each data section as available or unavailable:

```python
@dataclass(frozen=True)
class InsightGeneratorInput:
    ticker: str
    company: CompanyInfo | None
    market_data: MarketData | None
    sentiment: SentimentResult | None
    top_articles: list[ArticleSummary]   # up to 5 most recent
    events: list[ExtractedEvent]         # up to 5 most relevant
    data_availability: dict[str, bool]   # { "market_data": True, "news": False, ... }
```

1. **Prompt template:**

```
You are a financial research analyst. Generate a structured research overview for {{ ticker }} ({{ company.name }}).

Available data:
{% if data_availability.market_data %}
Current Price: {{ market_data.price }} {{ market_data.currency }} ({{ market_data.change_pct }}% today)
Market Cap: {{ market_data.market_cap_formatted }}
P/E Ratio: {{ market_data.pe_ratio or 'N/A' }}
52-Week Range: {{ market_data.week_52_low }} – {{ market_data.week_52_high }}
{% else %}
Market data: not available
{% endif %}

{% if data_availability.sentiment %}
News Sentiment: {{ sentiment.dominant }} ({{ sentiment.distribution.positive }}% positive,
{{ sentiment.distribution.neutral }}% neutral, {{ sentiment.distribution.negative }}% negative)
{% endif %}

{% if top_articles %}
Recent headlines:
{% for a in top_articles %}
- {{ a.title }} ({{ a.sentiment }}){% if a.summary %}: {{ a.summary }}{% endif %}
{% endfor %}
{% endif %}

{% if events %}
Key events detected:
{% for e in events %}
- {{ e.event_type }}: {{ e.description }}
{% endfor %}
{% endif %}

Generate a structured research overview. Do NOT provide buy/sell recommendations.
Respond ONLY with valid JSON:
{
  "company_overview": "string",
  "recent_developments": "string",
  "sentiment_overview": "string",
  "potential_drivers": "string",
  "potential_risks": "string",
  "ai_summary": "string"
}
```

1. Each field in the response is validated as a non-empty string. If a field is empty or missing, it is replaced with `"Insufficient data available for this section"`.
2. A fixed disclaimer string is appended to `InsightSections`: `"This content is AI-generated and does not constitute financial advice or a recommendation to buy or sell any security."` This is not generated by the LLM — it is a hardcoded domain constant.
3. `context.outputs.insights = InsightSections(...)`. Return `COMPLETE`.

---

### Step 9 — ReportAssembler

**Critical: YES** | **Max retries: 0**

**Business rules:**

1. This step is purely computational (no I/O, no LLM calls). It cannot fail due to external provider errors.
2. Assembles the `AnalysisReport` domain object from all `context.outputs` fields.
3. Computes `completeness`:

```python
def compute_completeness(context: PipelineContext) -> ReportCompleteness:
    critical_sections_available = (
        context.outputs.company is not None and
        (context.outputs.market_data is not None or
         len(context.outputs.deduplicated_articles) > 0)
    )
    if not critical_sections_available:
        return ReportCompleteness.MINIMAL

    optional_sections_available = sum([
        context.outputs.market_data is not None,
        len(context.outputs.deduplicated_articles) > 0,
        context.outputs.sentiment is not None,
        context.outputs.insights is not None,
    ])
    if optional_sections_available >= 3:
        return ReportCompleteness.COMPLETE
    return ReportCompleteness.PARTIAL
```

1. Assembles `partial_data_notices`: a list of human-readable strings describing which sections are unavailable and why. Example: `"Market data is unavailable. The stock overview panel could not be populated."`.
2. Assembles `data_sources`: only providers that were successfully queried AND returned usable data are listed.
3. Assembles `step_results`: a compact summary of each step's status and duration from `context.step_states`.
4. Writes `context.assembled_report = report`. Return `COMPLETE`.

---

## 6. State Transition Logic

### Run-Level State Machine

```
                    ┌─────────┐
                    │ ACCEPTED│ ← initial state on POST /analyze
                    └────┬────┘
                         │ pipeline task starts
                         ▼
                  ┌─────────────┐
                  │ IN_PROGRESS │
                  └──────┬──────┘
            ┌────────────┼─────────────┐
            │            │             │
            ▼            ▼             ▼
       ┌─────────┐  ┌────────┐  ┌───────────┐
       │COMPLETE │  │ FAILED │  │ TIMED_OUT │
       └─────────┘  └────────┘  └───────────┘
            │            │             │
            └────────────┴─────────────┘
                         │
                  (all are terminal)
```

**Transition guards (enforced by SQL `WHERE status IN (...)`):**

- `ACCEPTED → IN_PROGRESS`: only if current status is `ACCEPTED`
- `IN_PROGRESS → COMPLETE`: only if current status is `IN_PROGRESS`
- `IN_PROGRESS → FAILED`: only if current status is `IN_PROGRESS` or `ACCEPTED`
- `IN_PROGRESS → TIMED_OUT`: only if current status is `IN_PROGRESS` or `ACCEPTED`
- Terminal states (`COMPLETE`, `FAILED`, `TIMED_OUT`): no further transitions allowed

### Step-Level State Machine

```
PENDING → IN_PROGRESS → COMPLETE
                     └→ FAILED
PENDING → SKIPPED (can_execute() returned False)
```

---

## 7. Transaction Processing Logic

### Database Writes in the Pipeline

The pipeline makes the following database writes in sequence:

| When | Operation | Failure Behavior |
|---|---|---|
| Pipeline starts | `UPDATE analysis_runs SET status='in_progress'` | If fails: pipeline continues (Redis still tracks state) |
| Each step starts | `INSERT INTO pipeline_steps (status='in_progress')` | If fails: logged; pipeline continues |
| Each step ends | `UPDATE pipeline_steps SET status, duration, output_summary` | If fails: logged; pipeline continues |
| ReportAssembler completes | `UPDATE analysis_runs SET status='complete', report_data=...` | If fails: logged; user still received data via SSE |
| Critical step fails | `UPDATE analysis_runs SET status='failed'` | If fails: logged; Redis Pub/Sub still notified client |
| Timeout | `UPDATE analysis_runs SET status='timed_out'` | If fails: logged |

**All DB writes are fire-and-forget from the pipeline's perspective** (launched as independent `asyncio.create_task`). They do not block the event delivery path. This means a DB write failure does not delay or prevent the SSE event delivery to the client.

**Why not use a DB transaction across the pipeline:** The pipeline executes over 30–60 seconds. A long-lived database transaction of this duration would hold locks, consume connection pool slots, and potentially interfere with concurrent pipelines. The correct approach is atomic single-row updates per state transition.

---

## 8. Idempotency Safeguards

### Request-Level Idempotency

**Problem:** A user double-clicks "Analyze" or a network retry fires a second `POST /api/v1/analyze` for the same ticker from the same IP within the pipeline window.

**Solution:** Redis key `idem:{ip_address_hash}:{ticker}` → `run_id`, with TTL=120s (the maximum pipeline duration + buffer).

```python
idem_key = f"idem:{hashlib.sha256(ip_address.encode()).hexdigest()[:16]}:{ticker}"

existing_run_id = await redis.get(idem_key)
if existing_run_id:
    # Check if the run is still in-progress
    if await redis.exists(f"run:inprogress:{existing_run_id}"):
        return AnalyzeResponse(run_id=UUID(existing_run_id), status="accepted")
    # Run completed; allow new run
    await redis.delete(idem_key)

# Generate new run
new_run_id = uuid4()
await redis.set(idem_key, str(new_run_id), ex=120)
await redis.set(f"run:inprogress:{new_run_id}", "1", ex=120)
```

**IP address hashing:** The IP address is SHA-256 hashed before use as a key component. This means the actual IP address is never written to Redis as a key (though it is stored in `analysis_runs.ip_address` for rate limit auditing).

### Step-Level Idempotency

**Problem:** If a step is retried, it must not produce duplicate side effects (e.g., inserting two `pipeline_steps` rows for the same step).

**Solution:** `INSERT INTO pipeline_steps ... ON CONFLICT (run_id, step_index) DO UPDATE SET status=...`. The `UNIQUE (run_id, step_index)` constraint ensures this is safe.

### LLM Call Idempotency

**Problem:** If an LLM call is retried due to a parse error, the same prompt is re-sent. This is acceptable — LLM calls are stateless, and the cost is at most one extra inference call per step per run.

---

## 9. Concurrency Safety Rules

### Rule 1: No shared mutable state between concurrent pipeline runs

Each pipeline run gets its own `PipelineContext` instance. The `PipelineOrchestrator` is stateless between runs; all per-run state lives in the `PipelineContext`.

### Rule 2: LLM semaphore must be acquired before any LLM call

The `asyncio.Semaphore(3)` is shared across all concurrent pipeline runs. Any step that calls `LLMProvider` must acquire this semaphore first. Steps that forget to acquire it (programming error) will over-saturate Ollama. This is enforced by wrapping all LLM calls in `LLMProvider.call()`, which always acquires the semaphore internally — the steps never manage the semaphore directly.

### Rule 3: Redis Pub/Sub publish is fire-and-forget; pipeline does not wait for subscriber acknowledgment

The `EventBus.publish()` call returns when the message is written to the Redis List and published to the channel. It does not wait for the SSE router to relay it. This ensures the pipeline cannot be blocked by a slow client connection.

### Rule 4: Database connection pool exhaustion handling

`asyncpg` pool has `max_size=10`. If all connections are in use (pathological case: 10+ concurrent pipelines all hitting DB simultaneously), `await pool.acquire()` will wait up to `connection_timeout=10s`. If timeout fires, the specific DB write is skipped (logged as error); the pipeline continues. This is safe because DB writes are non-blocking fire-and-forget tasks.

### Rule 5: Watchdog cancellation is cooperative

The pipeline task handles `asyncio.CancelledError` in its outermost `try/except`. When the watchdog cancels the task via `task.cancel()`, the cancellation is raised at the next `await` point within the pipeline. The `except asyncio.CancelledError` block in the orchestrator handles cleanup (emit timeout event, mark DB row) and then returns (does not re-raise). This is the correct pattern — swallowing `CancelledError` is appropriate when the handler has completed its cleanup.

---

## 10. Failure Recovery Strategy

### Per-Step Recovery (non-critical steps)

On step failure, the orchestrator:

1. Records the `StepFailure` in `context.step_states`.
2. Sets the corresponding `context.outputs` field to `None` (for single-output steps) or an empty list (for collection-output steps).
3. The `ReportAssembler` reads from `context.outputs` and produces partial data notices for any `None` field.

This means the report is self-describing about its own completeness. No special "error report" type is needed — the same `AnalysisReport` structure accommodates full, partial, and minimal reports.

### Pipeline Recovery (critical step failure)

When a critical step fails (Step 1 or Step 9):

- Step 1 failure: all 8 subsequent steps are never executed; the SSE stream receives a single `pipeline_failed` terminal event; the client renders the empty state with the error message.
- Step 9 failure: This step is purely computational and should not fail unless there is a programming error. If it does fail, the SSE stream has already delivered all step events up to step 8; the client has all data except the assembled report. The client renders the data it received from the step events and shows a "Report assembly failed" notice.

### Re-submission Recovery

If a user sees a failed or timed-out pipeline, they submit the same ticker again. The idempotency key for the failed run has either expired (TTL=120s) or was cleared when the run entered a terminal state. The new submission creates a fresh run with a new `run_id`. There is no state contamination from the previous run.

---

## 11. Edge Case Matrix

| Scenario | Handling |
|---|---|
| Ticker resolves but yfinance returns empty price data | `MarketData.available = False`; step returns `COMPLETE` (not failed) with no-data marker |
| yfinance returns `None` for P/E ratio | `MarketData.pe_ratio = None`; rendered as "N/A" |
| RSS feed returns 0 articles after relevance filter | `raw_articles = []`; Steps 4–7 are `SKIPPED`; Sentiment/Events/Summaries all unavailable |
| All 20 articles are near-duplicates of the first | `deduplicated_articles = [articles[0]]`; all downstream steps operate on 1 article |
| LLM returns JSON with extra fields | Pydantic `model_validate()` ignores extra fields (no strict mode for LLM responses) |
| LLM returns truncated JSON (incomplete) | JSON parse fails → retry with corrective prompt hint |
| LLM classifies all articles as "neutral" | Dominant label = "Neutral / No Strong Signal"; `emerging_concern_flag = False` |
| Event extractor returns 0 events | `events = []`; Events section renders "No significant events identified" |
| Insight generator returns an empty section | Section is replaced with "Insufficient data available for this section" |
| Two concurrent runs for the same ticker | Allowed; each gets its own `run_id` and independent pipeline |
| User submits ticker mid-pipeline for same ticker | Idempotency key returns existing `run_id` if run is in-progress |
| Pipeline completes but DB write fails | Report is NOT in past-results API; user's SSE stream received all data |
| SSE connection drops mid-pipeline | On reconnect, client fetches buffered events from Redis List replay buffer |
| Client never connects to SSE (API-only use) | Pipeline runs normally; events are buffered in Redis List; TTL expires after 1 hour |
| Step 9 (ReportAssembler) receives all-None context | `completeness = MINIMAL`; report has empty sections with notices; not a failure |
| `price_history` has < 20 data points (new stock) | Trend calculation uses all available points; slope computation is valid for n ≥ 2 |
| `price_history` has 0 data points | `PriceHistory.available = False`; chart renders unavailable state |
| Company name contains special chars (e.g., "AT&T") | HTML-escaped in prompts via Jinja2 `{{ name | e }}` |
| Ollama takes > 45s per LLM call | `httpx` read timeout fires → `ExternalProviderError` with `is_retryable=True` → retry once |
| OpenAI API returns `context_length_exceeded` | Caught as `LLMParseError`-equivalent; step fails non-critically |
| Article URL is a paywall link | `content_available = False`; headline is used as sole prompt input for summarization |

---

## 12. LLM Provider Abstraction

```python
class LLMProvider(Protocol):
    model_name: str
    provider_name: str   # "ollama" | "openai"

    async def complete(
        self,
        prompt: str,
        max_tokens: int = 500,
        temperature: float = 0.1   # low temperature for structured/deterministic output
    ) -> str:
        """
        Returns the raw string response from the model.
        Raises ExternalProviderError on HTTP failure.
        Raises LLMParseError if the response is not valid JSON (when JSON is expected).
        """
        ...

class OllamaProvider:
    def __init__(self, base_url: str, model: str, semaphore: asyncio.Semaphore):
        self._base_url = base_url
        self._model = model
        self._semaphore = semaphore
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5, read=45))

    async def complete(self, prompt: str, max_tokens: int = 500, temperature: float = 0.1) -> str:
        async with self._semaphore:
            response = await self._client.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens}
                }
            )
            response.raise_for_status()
            return response.json()["response"]

class OpenAIProvider:
    def __init__(self, api_key: str, model: str, semaphore: asyncio.Semaphore):
        self._api_key = api_key
        self._model = model
        self._semaphore = semaphore
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(connect=5, read=30)
        )

    async def complete(self, prompt: str, max_tokens: int = 500, temperature: float = 0.1) -> str:
        async with self._semaphore:
            response = await self._client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
            )
            if response.status_code == 401:
                raise ExternalProviderError(
                    error_code="OPENAI_INVALID_KEY",
                    user_message="OpenAI API key is invalid or expired",
                    is_retryable=False
                )
            if response.status_code == 429:
                raise ExternalProviderError(
                    error_code="OPENAI_RATE_LIMITED",
                    user_message="OpenAI API rate limit exceeded",
                    is_retryable=True
                )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
```

---

## 13. Domain Exception Hierarchy

```python
class StockLensError(Exception):
    """Base exception for all domain errors."""

class ExternalProviderError(StockLensError):
    def __init__(self, error_code: str, user_message: str, is_retryable: bool):
        self.error_code = error_code
        self.user_message = user_message
        self.is_retryable = is_retryable

class LLMParseError(StockLensError):
    """LLM returned output that could not be parsed as expected JSON."""
    def __init__(self, step_name: str, raw_output: str):
        self.step_name = step_name
        self.raw_output = raw_output[:200]  # truncated; never log full LLM output

class TickerValidationError(StockLensError):
    """Ticker format is invalid; should be caught at HTTP layer before reaching domain."""

class PipelineCriticalFailure(StockLensError):
    """Critical step failed; pipeline must halt."""
    def __init__(self, step_name: str, failure: StepFailure):
        self.step_name = step_name
        self.failure = failure
```

---

## 14. Performance Optimization Checklist (Domain Layer)

| Optimization | Status | Implementation |
|---|---|---|
| Batch LLM calls for articles (3 concurrent) | Phase 1 | `asyncio.gather` + `asyncio.Semaphore(3)` |
| Market data + news retrieval parallelism | Phase 2 | Refactor orchestrator to `asyncio.gather` Steps 2 + 3 |
| Single LLM call for event extraction (whole corpus) | Phase 1 | Implemented as described above |
| SimHash deduplication O(n²) → O(n log n) | Phase 2 | LSH index over SimHash fingerprints |
| Ticker resolution caching (Redis) | Phase 1 | TTL-based Redis key |
| Market data caching (Redis) | Phase 1 | TTL 300s per ticker |
| LLM prompt length control | Phase 1 | Article content truncated to 500 chars; titles only for event extraction |
| Trend direction via slope (avoid full linear regression lib) | Phase 1 | Manual slope computation using least-squares formula on 20 points |
