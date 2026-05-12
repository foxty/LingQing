"""Task run log persistence — writes stdout/stderr to tenant-scoped files.

Lightweight file I/O (not a logging framework). Called once per run after
execution completes, regardless of task type or outcome.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def _get_tenant_task_logs_dir(data_root: str, tenant_id: int) -> str:
    """Tenant task log directory: {data_root}/tenants/tenant_{id}/task-logs/."""
    root_abs = os.path.abspath(data_root)
    path = os.path.abspath(os.path.join(root_abs, "tenants", f"tenant_{tenant_id}", "task-logs"))
    if path != root_abs and not path.startswith(f"{root_abs}{os.sep}"):
        raise ValueError("Invalid tenant task logs path resolution.")
    return path


@dataclass(frozen=True)
class RunLogPaths:
    """Relative paths to persisted log files (relative to DATA_ROOT)."""

    stdout_log_path: str
    stderr_log_path: str
    has_logs: bool = True


# ---------------------------------------------------------------------------
# RunLogWriter
# ---------------------------------------------------------------------------


class RunLogWriter:
    """Persists task run stdout/stderr to tenant-scoped log files.

    Usage:
        writer = RunLogWriter(data_root="/var/lib/lingqing/data")
        paths = writer.write_logs(
            tenant_id=1, task_id=42, run_id=101,
            attempt=1, started_at=run.started_at,
            stdout_content="...", stderr_content="...",
        )
        # paths.stdout_log_path -> "tenants/tenant_1/task-logs/task_42_run_101_..."
    """

    def __init__(self, data_root: str):
        self._data_root = os.path.abspath(data_root)

    def _build_filename_base(self, *, task_id: int, run_id: int, started_at: datetime, attempt: int) -> str:
        """Build filename base: task_{id}_run_{id}_{date}_attempt_{n}."""
        date_str = started_at.strftime("%Y%m%dT%H%M%SZ")
        return f"task_{task_id}_run_{run_id}_{date_str}_attempt_{attempt}"

    def _resolve_log_dir(self, tenant_id: int) -> str:
        """Resolve and ensure the tenant task log directory exists."""
        log_dir = _get_tenant_task_logs_dir(self._data_root, tenant_id)
        os.makedirs(log_dir, exist_ok=True)
        return log_dir

    def _to_relative_path(self, absolute_path: str) -> str:
        """Convert absolute path to relative (from DATA_ROOT)."""
        return os.path.relpath(absolute_path, self._data_root)

    def write_logs(
        self,
        *,
        tenant_id: int,
        task_id: int,
        run_id: int,
        attempt: int,
        started_at: datetime,
        stdout_content: str,
        stderr_content: str,
    ) -> RunLogPaths:
        """Write stdout/stderr to files and return relative paths.

        Args:
            tenant_id: Tenant scope for log storage
            task_id: Scheduled task ID
            run_id: TaskRun record ID
            attempt: Retry attempt number (1-based)
            started_at: Run start time (for filename timestamp)
            stdout_content: Stdout text (sandbox raw or formatted internal trace)
            stderr_content: Stderr text (sandbox raw or error trace)

        Returns:
            RunLogPaths with relative paths to written files
        """
        log_dir = self._resolve_log_dir(tenant_id)
        base = self._build_filename_base(task_id=task_id, run_id=run_id, started_at=started_at, attempt=attempt)

        stdout_path = os.path.join(log_dir, f"{base}.stdout.log")
        stderr_path = os.path.join(log_dir, f"{base}.stderr.log")

        with open(stdout_path, "w", encoding="utf-8") as f:
            f.write(stdout_content or "")

        with open(stderr_path, "w", encoding="utf-8") as f:
            f.write(stderr_content or "")

        logger.info(
            "Persisted task run logs: tenant=%s task_id=%s run_id=%s attempt=%s stdout=%d bytes stderr=%d bytes",
            tenant_id,
            task_id,
            run_id,
            attempt,
            len(stdout_content or ""),
            len(stderr_content or ""),
        )

        return RunLogPaths(
            stdout_log_path=self._to_relative_path(stdout_path),
            stderr_log_path=self._to_relative_path(stderr_path),
        )

    def resolve_absolute_path(self, relative_path: str) -> str:
        """Resolve a stored relative log path back to absolute.

        Used by the API endpoint to serve log files.
        """
        return os.path.join(self._data_root, relative_path)

    def read_log_content(self, relative_path: str, *, stream: str = "stdout") -> str:
        """Read log content from a stored relative path with security validation.

        Args:
            relative_path: Relative path from DATA_ROOT (e.g., from run.result)
            stream: Log stream type ('stdout' or 'stderr') for error messages

        Returns:
            Log file content as string

        Raises:
            FileNotFoundError: If log file doesn't exist on disk
            ValueError: If path resolution escapes DATA_ROOT
        """
        absolute_path = self.resolve_absolute_path(relative_path)

        # Security: ensure resolved path is within DATA_ROOT
        data_root_abs = os.path.abspath(self._data_root)
        resolved = os.path.abspath(absolute_path)
        if not resolved.startswith(f"{data_root_abs}{os.sep}"):
            raise ValueError(f"Invalid {stream} log path.")

        if not os.path.isfile(resolved):
            raise FileNotFoundError(f"{stream.capitalize()} log file not found on disk.")

        with open(resolved, encoding="utf-8", errors="replace") as f:
            return f.read()
