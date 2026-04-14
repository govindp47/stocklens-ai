"""Initial schema — all five tables.

Revision ID: 0001
Revises:     (none)
Create Date: 2026-03-27

Tables created:
  - analysis_runs
  - pipeline_steps
  - system_metrics_hourly
  - ticker_resolution_cache
  - rate_limit_log

Constraints:
  - CHECK constraints inline in CREATE TABLE
  - FK from pipeline_steps.run_id → analysis_runs.run_id ON DELETE CASCADE
  - UNIQUE constraints on business keys

Indexes:
  - All created with CREATE INDEX CONCURRENTLY via op.execute() inside a
    AUTOCOMMIT isolation-level context (required for CONCURRENTLY).

updated_at trigger:
  - Applied to analysis_runs (the only mutable table requiring audit timestamps).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# Revision identifiers used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    # ── 1. analysis_runs ────────────────────────────────────────────────────
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "run_id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(25), nullable=False),
        sa.Column("status", sa.String(20), server_default="accepted", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("llm_provider", sa.String(20), server_default="ollama", nullable=False),
        sa.Column("llm_model", sa.String(150), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),  # INET stored as text via asyncpg
        sa.Column("report_data", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("steps_total", sa.SmallInteger(), server_default="9", nullable=False),
        sa.Column("steps_completed", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("steps_failed", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("is_deleted", sa.Boolean(), server_default="FALSE", nullable=False),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="analysis_runs_pkey"),
        sa.UniqueConstraint("run_id", name="analysis_runs_run_id_unique"),
        sa.CheckConstraint(
            "status IN ('accepted', 'in_progress', 'complete', 'failed', 'timed_out')",
            name="analysis_runs_status_check",
        ),
        sa.CheckConstraint(
            "llm_provider IN ('ollama', 'openai', 'nvidia')",
            name="analysis_runs_llm_provider_check",
        ),
        sa.CheckConstraint(
            "steps_completed >= 0 AND steps_completed <= steps_total",
            name="analysis_runs_steps_completed_range",
        ),
        sa.CheckConstraint(
            "steps_failed >= 0 AND steps_failed <= steps_total",
            name="analysis_runs_steps_failed_range",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="analysis_runs_duration_positive",
        ),
        sa.CheckConstraint(
            r"ticker ~ '^[A-Z]{1,20}(\.[A-Z]{1,5})?$'",
            name="analysis_runs_ticker_format",
        ),
    )

    # ── 2. pipeline_steps ───────────────────────────────────────────────────
    op.create_table(
        "pipeline_steps",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("step_index", sa.SmallInteger(), nullable=False),
        sa.Column("step_name", sa.String(60), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_summary", sa.JSON(), nullable=True),
        sa.Column("output_summary", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(60), nullable=True),
        sa.Column("retry_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id", name="pipeline_steps_pkey"),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["analysis_runs.run_id"],
            name="pipeline_steps_run_fk",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "step_index", name="pipeline_steps_unique_step_per_run"),
        sa.CheckConstraint(
            "status IN ('pending', 'in_progress', 'complete', 'failed', 'skipped')",
            name="pipeline_steps_status_check",
        ),
        sa.CheckConstraint(
            "step_index BETWEEN 1 AND 9",
            name="pipeline_steps_step_index_range",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="pipeline_steps_duration_positive",
        ),
    )

    # ── 3. system_metrics_hourly ────────────────────────────────────────────
    op.create_table(
        "system_metrics_hourly",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("bucket_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("bucket_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("runs_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("runs_complete", sa.Integer(), server_default="0", nullable=False),
        sa.Column("runs_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("runs_timed_out", sa.Integer(), server_default="0", nullable=False),
        sa.Column("p50_duration_ms", sa.Integer(), nullable=True),
        sa.Column("p95_duration_ms", sa.Integer(), nullable=True),
        sa.Column("p99_duration_ms", sa.Integer(), nullable=True),
        sa.Column("unique_tickers", sa.Integer(), server_default="0", nullable=False),
        sa.Column("avg_articles_per_run", sa.Numeric(6, 2), nullable=True),
        sa.Column("rate_limit_hits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("step_failures_json", sa.JSON(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="system_metrics_hourly_pkey"),
        sa.UniqueConstraint("bucket_start", name="system_metrics_hourly_bucket_unique"),
        sa.CheckConstraint(
            "bucket_end > bucket_start",
            name="system_metrics_hourly_bucket_order",
        ),
        sa.CheckConstraint(
            "runs_total >= 0 AND runs_complete >= 0 AND runs_failed >= 0 AND runs_timed_out >= 0",
            name="system_metrics_hourly_runs_non_negative",
        ),
    )

    # ── 4. ticker_resolution_cache ──────────────────────────────────────────
    op.create_table(
        "ticker_resolution_cache",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(25), nullable=False),
        sa.Column("company_name", sa.String(200), nullable=True),
        sa.Column("exchange", sa.String(20), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("industry", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("country", sa.String(60), nullable=True),
        sa.Column("is_resolvable", sa.Boolean(), server_default="TRUE", nullable=False),
        sa.Column(
            "resolved_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="ticker_resolution_cache_pkey"),
        sa.UniqueConstraint("ticker", name="ticker_resolution_cache_ticker_unique"),
        sa.CheckConstraint(
            r"ticker ~ '^[A-Z]{1,20}(\.[A-Z]{1,5})?$'",
            name="ticker_resolution_cache_ticker_format",
        ),
        sa.CheckConstraint(
            "expires_at > resolved_at",
            name="ticker_resolution_cache_expires_after_resolved",
        ),
    )

    # ── 5. rate_limit_log ───────────────────────────────────────────────────
    op.create_table(
        "rate_limit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("endpoint", sa.String(100), nullable=False),
        sa.Column(
            "rejected_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("window_count", sa.Integer(), nullable=True),
        sa.Column("window_seconds", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="rate_limit_log_pkey"),
    )

    # ── updated_at trigger on analysis_runs ─────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_analysis_runs_updated_at
            BEFORE UPDATE ON analysis_runs
            FOR EACH ROW
            EXECUTE FUNCTION set_updated_at();
    """)

    # ── Indexes (CREATE INDEX CONCURRENTLY requires AUTOCOMMIT) ─────────────
    # Alembic's op.execute() runs inside a transaction by default.
    # CONCURRENTLY cannot run inside a transaction, so we use the
    # connection's execution_options to set ISOLATION_LEVEL_AUTOCOMMIT.
    connection = op.get_bind()
    connection.execute(sa.text("COMMIT"))  # end the current transaction

    # analysis_runs indexes
    connection.execute(sa.text(
        "CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_runs_run_id "
        "ON analysis_runs (run_id)"
    ))
    connection.execute(sa.text(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_runs_ticker_created "
        "ON analysis_runs (ticker, created_at DESC) "
        "WHERE is_deleted = FALSE"
    ))
    connection.execute(sa.text(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_runs_created_status "
        "ON analysis_runs (created_at, status) "
        "WHERE is_deleted = FALSE"
    ))
    connection.execute(sa.text(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_analysis_runs_in_progress "
        "ON analysis_runs (created_at) "
        "WHERE status IN ('accepted', 'in_progress') AND is_deleted = FALSE"
    ))

    # pipeline_steps indexes
    connection.execute(sa.text(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pipeline_steps_run_id "
        "ON pipeline_steps (run_id)"
    ))
    connection.execute(sa.text(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pipeline_steps_step_name_status "
        "ON pipeline_steps (step_name, status) "
        "WHERE status = 'failed'"
    ))

    # system_metrics_hourly index
    connection.execute(sa.text(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_system_metrics_hourly_bucket "
        "ON system_metrics_hourly (bucket_start DESC)"
    ))

    # ticker_resolution_cache index
    connection.execute(sa.text(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ticker_resolution_cache_expires "
        "ON ticker_resolution_cache (expires_at) "
        "WHERE is_resolvable = TRUE"
    ))

    # rate_limit_log indexes
    connection.execute(sa.text(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rate_limit_log_rejected_at "
        "ON rate_limit_log (rejected_at)"
    ))
    connection.execute(sa.text(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_rate_limit_log_ip "
        "ON rate_limit_log (ip_address, rejected_at DESC)"
    ))

    # ── Database least-privilege grants (07_SECURITY_MODEL.md §4.3) ─────────
    # Ensure the application role exists before granting.
    # In production, this role is created by the infrastructure provisioning
    # step; IF NOT EXISTS makes the migration idempotent in all environments.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'stocklens_app') THEN
                CREATE ROLE stocklens_app LOGIN PASSWORD 'apppassword';
            END IF;
        END
        $$;
    """)

    # CRUD grants on application tables
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON analysis_runs TO stocklens_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON pipeline_steps TO stocklens_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON system_metrics_hourly TO stocklens_app;")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ticker_resolution_cache TO stocklens_app;")

    # rate_limit_log is append-only: no UPDATE or DELETE for the app user
    op.execute("GRANT SELECT, INSERT ON rate_limit_log TO stocklens_app;")

    # Sequence usage (needed for autoincrement INSERTs)
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO stocklens_app;")

    # Explicitly deny DDL rights — no CREATE TABLE / ALTER TABLE / DROP TABLE
    op.execute("REVOKE CREATE ON SCHEMA public FROM stocklens_app;")

    # Deny access to the pg_authid system catalog (prevents reading password hashes)
    op.execute("REVOKE ALL ON pg_catalog.pg_authid FROM stocklens_app;")


def downgrade() -> None:
    # ── Drop indexes ────────────────────────────────────────────────────────
    connection = op.get_bind()
    connection.execute(sa.text("COMMIT"))

    for idx in [
        "idx_rate_limit_log_ip",
        "idx_rate_limit_log_rejected_at",
        "idx_ticker_resolution_cache_expires",
        "idx_system_metrics_hourly_bucket",
        "idx_pipeline_steps_step_name_status",
        "idx_pipeline_steps_run_id",
        "idx_analysis_runs_in_progress",
        "idx_analysis_runs_created_status",
        "idx_analysis_runs_ticker_created",
        "idx_analysis_runs_run_id",
    ]:
        connection.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {idx}"))

    # ── Drop trigger and function ────────────────────────────────────────────
    op.execute("DROP TRIGGER IF EXISTS trg_analysis_runs_updated_at ON analysis_runs")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")

    # ── Drop tables in reverse dependency order ──────────────────────────────
    op.drop_table("rate_limit_log")
    op.drop_table("ticker_resolution_cache")
    op.drop_table("system_metrics_hourly")
    op.drop_table("pipeline_steps")
    op.drop_table("analysis_runs")
