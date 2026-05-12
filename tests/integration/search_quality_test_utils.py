from __future__ import annotations

"""Shared utilities for search quality benchmark integration tests.

This module centralizes common benchmark logic so API connector, document,
and asset benchmark suites use the same schema checks and top-N assertions.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

SEARCH_QUALITY_MODES = ("fts", "vector", "hybrid")
SEARCH_QUALITY_REPORT_PATH = Path("tests/integration/artifacts/search_quality_metrics.jsonl")


def get_search_quality_report_path() -> Path:
    """Resolve artifact path, allowing override via env for CLI temporary runs."""
    raw = os.getenv("SEARCH_QUALITY_REPORT_PATH", "").strip()
    if raw:
        return Path(raw)
    return SEARCH_QUALITY_REPORT_PATH


def should_write_search_quality_report() -> bool:
    """Return whether benchmark result rows should be persisted to artifact file."""
    raw = os.getenv("SEARCH_QUALITY_WRITE_REPORT", "0").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def get_search_quality_modes() -> list[str]:
    """Get benchmark modes from env var, defaulting to all modes in one run."""
    raw = os.getenv("SEARCH_QUALITY_MODES", "fts,vector,hybrid")
    modes = [part.strip().lower() for part in raw.split(",") if part.strip()]
    valid = [mode for mode in modes if mode in SEARCH_QUALITY_MODES]
    return valid or ["fts"]


def resolve_top_n_for_mode(
    *,
    mode: str,
    query_top_n: int | None,
    query_top_n_by_mode: dict[str, Any] | None,
    default_top_n: int | None,
    default_top_n_by_mode: dict[str, Any] | None,
) -> int:
    """Resolve per-query top-N requirement with query-level overrides first."""
    top_n: int | None = None

    if isinstance(query_top_n_by_mode, dict):
        mode_value = query_top_n_by_mode.get(mode)
        if isinstance(mode_value, int):
            top_n = mode_value

    if top_n is None and isinstance(query_top_n, int):
        top_n = query_top_n

    if top_n is None and isinstance(default_top_n_by_mode, dict):
        mode_value = default_top_n_by_mode.get(mode)
        if isinstance(mode_value, int):
            top_n = mode_value

    if top_n is None and isinstance(default_top_n, int):
        top_n = default_top_n

    if top_n is None:
        top_n = 5

    if top_n < 1:
        raise ValueError(f"top_n must be >= 1, got {top_n} for mode={mode}")

    return top_n


def write_search_quality_result(
    *,
    resource: str,
    mode: str,
    case_id: str,
    query: str,
    expected_source_id: str,
    top_n: int,
    found_rank: int | None,
    passed: bool,
) -> None:
    """Append one row-level top-N result record for downstream analysis."""
    if not should_write_search_quality_report():
        return

    report_path = get_search_quality_report_path()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "resource": resource,
        "mode": mode,
        "case_id": case_id,
        "query": query,
        "expected_source_id": expected_source_id,
        "top_n": top_n,
        "found_rank": found_rank,
        "passed": passed,
    }
    with report_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True) + "\n")


async def assert_column_exists(schema_session: AsyncSession, table_name: str, column_name: str) -> None:
    """Fail fast if a required migration-provided column is missing."""
    exists = await schema_session.scalar(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {"table_name": table_name, "column_name": column_name},
    )
    if not exists:
        raise AssertionError(
            f"Missing required column public.{table_name}.{column_name}. "
            "Run Alembic migrations (e.g. `uv run alembic upgrade head`) before integration tests."
        )


async def assert_index_exists(schema_session: AsyncSession, index_name: str) -> None:
    """Fail fast if a required migration-provided index is missing."""
    exists = await schema_session.scalar(
        text(
            """
            SELECT 1
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname = :index_name
            LIMIT 1
            """
        ),
        {"index_name": index_name},
    )
    if not exists:
        raise AssertionError(
            f"Missing required index public.{index_name}. "
            "Run Alembic migrations (e.g. `uv run alembic upgrade head`) before integration tests."
        )
