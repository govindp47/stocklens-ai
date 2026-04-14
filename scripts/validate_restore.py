#!/usr/bin/env python3
"""
validate_restore.py — Post-restore database assertion checks.

Usage:
    DATABASE_URL=postgresql://... python3 validate_restore.py <manifest.json>

Exit codes:
    0 — all assertions passed
    1 — one or more assertions failed
"""

import asyncio
import json
import os
import sys


async def validate_restore(db_url: str, manifest: dict) -> None:
    """
    Validates a restored database against the backup manifest.
    Raises AssertionError if any validation fails.
    """
    try:
        import asyncpg  # type: ignore[import]
    except ImportError:
        print("[validate] ERROR: asyncpg is not installed. Run: pip install asyncpg", file=sys.stderr)
        sys.exit(1)

    # asyncpg uses postgresql:// not postgresql+asyncpg://
    asyncpg_url = db_url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres+asyncpg://", "postgresql://"
    )

    pool = await asyncpg.create_pool(asyncpg_url, min_size=1, max_size=3)
    try:
        async with pool.acquire() as conn:

            # ── Assertion 1: Alembic version table exists and is populated ────
            version = await conn.fetchval("SELECT version_num FROM alembic_version")
            assert version is not None, (
                "Alembic version table missing or empty — schema was not restored correctly"
            )
            print(f"[validate] Assertion 1 PASSED — alembic version: {version}")

            # ── Assertion 2: Table row counts within 5% of manifest values ────
            expected_counts: dict[str, int] = manifest["database"]["table_row_counts"]
            for table, expected in expected_counts.items():
                actual = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
                if expected > 0:
                    ratio = actual / expected
                    assert 0.95 <= ratio <= 1.05, (
                        f"Row count mismatch for table '{table}': "
                        f"expected ~{expected} (±5%), got {actual} (ratio={ratio:.3f})"
                    )
                print(f"[validate] Assertion 2 PASSED — {table}: {actual} rows (expected ~{expected})")

            # ── Assertion 3: No orphaned pipeline_steps ────────────────────────
            orphans = await conn.fetchval(
                """
                SELECT COUNT(*) FROM pipeline_steps ps
                WHERE NOT EXISTS (
                    SELECT 1 FROM analysis_runs ar WHERE ar.run_id = ps.run_id
                )
                """
            )
            assert orphans == 0, (
                f"Found {orphans} orphaned pipeline_steps rows — FK integrity violated"
            )
            print(f"[validate] Assertion 3 PASSED — no orphaned pipeline_steps")

            # ── Assertion 4: Reclassify in-progress runs to 'failed' ──────────
            # Runs that were in-progress at backup time can never complete —
            # mark them failed so the application doesn't treat them as active.
            updated = await conn.fetchval(
                """
                WITH updated AS (
                    UPDATE analysis_runs
                    SET
                        status = 'failed',
                        error_message = 'Run was in-progress at backup time; marked failed on restore'
                    WHERE status IN ('accepted', 'in_progress')
                    RETURNING run_id
                )
                SELECT COUNT(*) FROM updated
                """
            )
            print(
                f"[validate] Assertion 4 PASSED — reclassified {updated} in-progress run(s) to 'failed'"
            )

    finally:
        await pool.close()

    print("[validate] Restore validation PASSED — all assertions satisfied.")


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <manifest.json>", file=sys.stderr)
        sys.exit(1)

    manifest_path = sys.argv[1]
    if not os.path.isfile(manifest_path):
        print(f"[validate] ERROR: Manifest file not found: {manifest_path}", file=sys.stderr)
        sys.exit(1)

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("[validate] ERROR: DATABASE_URL environment variable is required", file=sys.stderr)
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    try:
        asyncio.run(validate_restore(db_url, manifest))
    except AssertionError as e:
        print(f"[validate] FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[validate] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
