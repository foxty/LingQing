"""Unit tests for RunLogWriter."""

import os
from datetime import UTC, datetime

import pytest

from apps.shared.tasks.run_log_writer import RunLogPaths, RunLogWriter


@pytest.fixture
def tmp_data_root(tmp_path):
    """Create a temporary data root directory."""
    return str(tmp_path)


@pytest.fixture
def writer(tmp_data_root):
    return RunLogWriter(data_root=tmp_data_root)


class TestRunLogWriter:
    def test_write_logs_creates_files(self, writer, tmp_data_root):
        started_at = datetime(2026, 5, 29, 14, 30, 0, tzinfo=UTC)
        paths = writer.write_logs(
            tenant_id=1,
            task_id=42,
            run_id=101,
            attempt=1,
            started_at=started_at,
            stdout_content="hello world\nline 2",
            stderr_content="warning: something",
        )

        assert isinstance(paths, RunLogPaths)
        assert paths.has_logs is True

        # Verify files exist on disk
        stdout_abs = writer.resolve_absolute_path(paths.stdout_log_path)
        stderr_abs = writer.resolve_absolute_path(paths.stderr_log_path)
        assert os.path.isfile(stdout_abs)
        assert os.path.isfile(stderr_abs)

        # Verify content
        with open(stdout_abs) as f:
            assert f.read() == "hello world\nline 2"
        with open(stderr_abs) as f:
            assert f.read() == "warning: something"

    def test_write_logs_filename_pattern(self, writer, tmp_data_root):
        started_at = datetime(2026, 5, 29, 14, 30, 0, tzinfo=UTC)
        paths = writer.write_logs(
            tenant_id=1,
            task_id=42,
            run_id=101,
            attempt=3,
            started_at=started_at,
            stdout_content="out",
            stderr_content="err",
        )

        expected_base = "task_42_run_101_20260529T143000Z_attempt_3"
        assert paths.stdout_log_path.endswith(f"{expected_base}.stdout.log")
        assert paths.stderr_log_path.endswith(f"{expected_base}.stderr.log")

    def test_write_logs_tenant_scoped_directory(self, writer, tmp_data_root):
        started_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        paths = writer.write_logs(
            tenant_id=5,
            task_id=10,
            run_id=20,
            attempt=1,
            started_at=started_at,
            stdout_content="",
            stderr_content="",
        )

        assert "tenant_5" in paths.stdout_log_path
        assert "task-logs" in paths.stdout_log_path

    def test_write_logs_relative_paths(self, writer, tmp_data_root):
        started_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        paths = writer.write_logs(
            tenant_id=1,
            task_id=1,
            run_id=1,
            attempt=1,
            started_at=started_at,
            stdout_content="test",
            stderr_content="test",
        )

        # Paths should be relative (not start with /)
        assert not os.path.isabs(paths.stdout_log_path)
        assert not os.path.isabs(paths.stderr_log_path)

    def test_write_logs_empty_content(self, writer):
        started_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        paths = writer.write_logs(
            tenant_id=1,
            task_id=1,
            run_id=1,
            attempt=1,
            started_at=started_at,
            stdout_content="",
            stderr_content="",
        )

        stdout_abs = writer.resolve_absolute_path(paths.stdout_log_path)
        with open(stdout_abs) as f:
            assert f.read() == ""

    def test_write_logs_none_content_treated_as_empty(self, writer):
        started_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
        paths = writer.write_logs(
            tenant_id=1,
            task_id=1,
            run_id=1,
            attempt=1,
            started_at=started_at,
            stdout_content=None,  # type: ignore[arg-type]
            stderr_content=None,  # type: ignore[arg-type]
        )

        stdout_abs = writer.resolve_absolute_path(paths.stdout_log_path)
        with open(stdout_abs) as f:
            assert f.read() == ""

    def test_resolve_absolute_path(self, writer, tmp_data_root):
        relative = os.path.join("tenants", "tenant_1", "task-logs", "test.log")
        absolute = writer.resolve_absolute_path(relative)
        assert absolute == os.path.join(os.path.abspath(tmp_data_root), relative)
