from __future__ import annotations

from prometheus_client import Counter, Histogram

# ── Pipeline-level metrics ─────────────────────────────────────────────────

pipeline_runs_total = Counter(
    "stocklens_pipeline_runs_total",
    "Total number of pipeline runs by completion status",
    ["status"],  # labels: complete | failed | timeout
)

pipeline_duration_seconds = Histogram(
    "stocklens_pipeline_duration_seconds",
    "End-to-end pipeline execution duration in seconds",
    ["ticker_type"],  # labels: known | unknown
    buckets=[5.0, 10.0, 20.0, 30.0, 45.0, 60.0, 75.0, 90.0, 120.0],
)

# ── Step-level metrics ─────────────────────────────────────────────────────

step_duration_seconds = Histogram(
    "stocklens_step_duration_seconds",
    "Duration of each pipeline step in seconds",
    ["step_name"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0],
)

# ── LLM-level metrics ──────────────────────────────────────────────────────

llm_inference_duration_seconds = Histogram(
    "stocklens_llm_inference_duration_seconds",
    "Duration of LLM inference calls in seconds",
    ["provider", "step_name"],  # provider: ollama | openai
    buckets=[1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 45.0, 60.0],
)
