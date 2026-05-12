"""Unit tests for liveapp_job task type domain models."""

from apps.shared.tasks.domain import (
    TASK_TYPE_LIVEAPP_JOB,
    LiveAppJobTaskConfig,
    is_valid_scheduled_task_type,
)


class TestLiveAppJobDomain:
    """Tests for liveapp_job domain types."""

    def test_task_type_constant_defined(self):
        """Verify TASK_TYPE_LIVEAPP_JOB constant exists."""
        assert TASK_TYPE_LIVEAPP_JOB == "liveapp_job"

    def test_task_type_is_valid(self):
        """Verify liveapp_job is recognized as valid task type."""
        assert is_valid_scheduled_task_type("liveapp_job") is True

    def test_liveapp_job_task_config_creation(self):
        """Test creating LiveAppJobTaskConfig with required fields."""
        config: LiveAppJobTaskConfig = {
            "app_id": 123,
            "job_name": "sync_weather",
            "entrypoint": "jobs/sync_weather.py",
            "environment": "prod",
        }

        assert config["app_id"] == 123
        assert config["job_name"] == "sync_weather"
        assert config["entrypoint"] == "jobs/sync_weather.py"
        assert config["environment"] == "prod"

    def test_liveapp_job_task_config_with_optional_fields(self):
        """Test LiveAppJobTaskConfig with optional job_params."""
        config: LiveAppJobTaskConfig = {
            "app_id": 456,
            "job_name": "daily_report",
            "entrypoint": "jobs/daily_report.py",
            "environment": "dev",
            "job_params": {"report_type": "summary", "include_charts": True},
        }

        assert config["job_params"]["report_type"] == "summary"
        assert config["job_params"]["include_charts"] is True

    def test_sandbox_execution_params_for_liveapp_job(self):
        """Test get_sandbox_execution_params() for liveapp_job tasks."""
        from datetime import datetime, timezone

        from apps.shared.tasks.domain import ScheduledTaskDomain

        task = ScheduledTaskDomain(
            id=1,
            tenant_id=7,
            user_id=1,
            name="test_job",
            task_type=TASK_TYPE_LIVEAPP_JOB,
            task_config={
                "app_id": 789,
                "job_name": "etl_pipeline",
                "entrypoint": "jobs/etl_pipeline.py",
                "environment": "prod",
            },
            schedule_type="once",
            schedule_spec={"run_at": "2024-01-01T00:00:00Z"},
            status="pending",
            next_run_at=None,
            last_run_at=None,
            notification_channels=None,
            error_message=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        params = task.get_sandbox_execution_params()

        assert params is not None
        # target_kind removed - use task.task_type directly
        assert params.entrypoint == "jobs/etl_pipeline.py"
        assert params.target_id == "789:etl_pipeline"
        # Command template includes environment setup (transparent to job script)
        assert "cd /app_root" in params.command_template
        assert "pip install -q --cache-dir /tmp/pip-cache --target .venv -r requirements.txt" in params.command_template
        assert "PYTHONPATH=/app_root:/app_root/.venv" in params.command_template
        assert "python jobs/etl_pipeline.py" in params.command_template

    def test_sandbox_execution_params_target_id_format(self):
        """Verify target_id follows app_id:job_name format."""
        from datetime import datetime, timezone

        from apps.shared.tasks.domain import ScheduledTaskDomain

        task = ScheduledTaskDomain(
            id=2,
            tenant_id=7,
            user_id=1,
            name="test_job",
            task_type=TASK_TYPE_LIVEAPP_JOB,
            task_config={
                "app_id": 999,
                "job_name": "test_job",
                "entrypoint": "jobs/test.py",
            },
            schedule_type="once",
            schedule_spec={"run_at": "2024-01-01T00:00:00Z"},
            status="pending",
            next_run_at=None,
            last_run_at=None,
            notification_channels=None,
            error_message=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        params = task.get_sandbox_execution_params()

        # Should be in format "app_id:job_name"
        assert ":" in params.target_id
        parts = params.target_id.split(":")
        assert len(parts) == 2
        assert parts[0] == "999"
        assert parts[1] == "test_job"
