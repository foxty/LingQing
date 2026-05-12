"""Unit tests for live app workspace job file support."""

import pytest

from apps.shared.live_app.workspace import (
    ALLOWED_APP_FILE_SUFFIXES,
    _validate_job_path,
)


class TestWorkspaceJobSupport:
    """Tests for workspace job file validation."""

    def test_py_suffix_allowed(self):
        """Verify .py files are allowed in workspace."""
        assert ".py" in ALLOWED_APP_FILE_SUFFIXES

    def test_txt_suffix_allowed(self):
        """Verify .txt files (for requirements.txt) are allowed."""
        assert ".txt" in ALLOWED_APP_FILE_SUFFIXES

    def test_validate_job_path_valid(self):
        """Test valid job paths pass validation."""
        # Should not raise
        _validate_job_path("jobs/sync_api.py")
        _validate_job_path("jobs/daily_report.py")
        _validate_job_path("jobs/etl/weather_sync.py")

    def test_validate_job_path_missing_jobs_prefix(self):
        """Test paths without jobs/ prefix fail validation."""
        with pytest.raises(ValueError, match="must be under 'jobs/' directory"):
            _validate_job_path("sync_api.py")

        with pytest.raises(ValueError, match="must be under 'jobs/' directory"):
            _validate_job_path("scripts/test.py")

    def test_validate_job_path_wrong_extension(self):
        """Test non-.py files in jobs/ directory fail validation."""
        with pytest.raises(ValueError, match="must have .py extension"):
            _validate_job_path("jobs/config.json")

        with pytest.raises(ValueError, match="must have .py extension"):
            _validate_job_path("jobs/readme.md")

    def test_validate_job_path_edge_cases(self):
        """Test edge cases for job path validation."""
        # Hidden files should pass (though probably not desired)
        _validate_job_path("jobs/.hidden.py")

        # Nested directories should work
        _validate_job_path("jobs/subdir/deep/nested.py")
