#!/usr/bin/env python3
"""Standalone CLI runner for search quality benchmark suites.

This command is intentionally decoupled from CI wiring and is designed for
manual/local analysis of FTS/vector/hybrid quality.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

VALID_MODES = ("fts", "vector", "hybrid")
TEST_FILES = [
    "tests/integration/test_search_quality_benchmark.py",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run search quality benchmark and print summarized metrics.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--modes",
        default="fts,vector,hybrid",
        help="Comma-separated benchmark modes to run (default: fts,vector,hybrid)",
    )
    parser.add_argument(
        "--report-path",
        default="",
        help="Optional path to persist report JSONL; if omitted, report is temporary and not saved.",
    )
    parser.add_argument(
        "--reset-report",
        action="store_true",
        help="Delete existing report file before running (requires --report-path).",
    )
    parser.add_argument(
        "--pytest-args",
        default="",
        help="Extra pytest args (e.g. '-k api_connector').",
    )

    args = parser.parse_args()

    raw_modes = [part.strip().lower() for part in args.modes.split(",") if part.strip()]
    invalid_modes = [mode for mode in raw_modes if mode not in VALID_MODES]
    if invalid_modes:
        parser.error(f"Invalid --modes value(s): {', '.join(invalid_modes)}. Allowed values: {', '.join(VALID_MODES)}")

    if args.reset_report and not args.report_path.strip():
        parser.error("--reset-report requires --report-path")

    args.modes = ",".join(raw_modes)
    return args


def _run_pytest(modes: str, pytest_args: str, write_report: bool, report_path: Path | None = None) -> int:
    env = os.environ.copy()
    env["SEARCH_QUALITY_MODES"] = modes
    env["SEARCH_QUALITY_WRITE_REPORT"] = "1" if write_report else "0"
    if report_path is not None:
        env["SEARCH_QUALITY_REPORT_PATH"] = str(report_path)

    cmd = [sys.executable, "-m", "pytest", *TEST_FILES, "-q"]
    if pytest_args.strip():
        cmd.extend(pytest_args.strip().split())

    print(f"Running benchmark with SEARCH_QUALITY_MODES={modes}")
    print("Command:", " ".join(cmd))
    completed = subprocess.run(cmd, env=env)
    return completed.returncode


def _read_records_since(start_utc: datetime, report_path: Path) -> list[dict[str, Any]]:
    if not report_path.exists():
        return []

    records: list[dict[str, Any]] = []
    with report_path.open("r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue

            ts_raw = row.get("timestamp_utc")
            if not isinstance(ts_raw, str):
                continue

            try:
                ts = datetime.fromisoformat(ts_raw)
            except ValueError:
                continue

            if ts >= start_utc:
                records.append(row)

    return records


def _print_summary(records: list[dict[str, Any]]) -> None:
    if not records:
        print("No benchmark records found for this run.")
        return

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        mode = str(row.get("mode", "unknown"))
        grouped[mode].append(row)

    print("\nSearch Quality Benchmark Summary")
    print("=" * 40)
    for mode in sorted(grouped.keys()):
        print(f"\nMode: {mode}")
        headers = ["resource", "case_id", "query", "top_n", "rank", "passed"]
        rows: list[list[str]] = []

        for row in grouped[mode]:
            resource = str(row.get("resource", "unknown"))
            case_id = str(row.get("case_id", "-"))
            query = str(row.get("query", "-"))
            top_n = str(row.get("top_n", "-"))
            rank = str(row.get("found_rank", "-"))
            passed = "yes" if bool(row.get("passed")) else "no"
            rows.append([resource, case_id, query, top_n, rank, passed])

        if not rows:
            print("  (no rows)")
            continue

        widths = [len(h) for h in headers]
        for table_row in rows:
            for idx, cell in enumerate(table_row):
                widths[idx] = max(widths[idx], len(cell))

        def _fmt_row(cells: list[str]) -> str:
            return " | ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

        print(_fmt_row(headers))
        print("-+-".join("-" * w for w in widths))
        for table_row in rows:
            print(_fmt_row(table_row))


def main() -> int:
    args = _parse_args()
    persist_report_path: Path | None = Path(args.report_path).expanduser() if args.report_path.strip() else None

    effective_report_path: Path
    temp_report_path: Path | None = None
    if persist_report_path is not None:
        effective_report_path = persist_report_path
    else:
        fd, temp_path = tempfile.mkstemp(prefix="search-quality-", suffix=".jsonl")
        os.close(fd)
        temp_report_path = Path(temp_path)
        effective_report_path = temp_report_path

    if args.reset_report and effective_report_path.exists():
        effective_report_path.unlink()

    run_started = datetime.now(UTC)
    exit_code = _run_pytest(
        modes=args.modes,
        pytest_args=args.pytest_args,
        write_report=True,
        report_path=effective_report_path,
    )

    records = _read_records_since(run_started, report_path=effective_report_path)
    _print_summary(records)

    if temp_report_path is not None:
        temp_report_path.unlink(missing_ok=True)
        print("Report not persisted (temporary report used for console summary).")

    if persist_report_path is not None:
        print(f"\nArtifact: {persist_report_path}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
