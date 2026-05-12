"""Unit tests for schedule_task tool with dynamic task_config parameter.

These tests verify the ScheduleTaskSchema validation logic for the
task_type + task_config pattern.
"""

import pytest
from pydantic import ValidationError

from apps.shared.tasks.domain import (
    TASK_TYPE_AGENT_RUN,
    TASK_TYPE_LIVEAPP_JOB,
    TASK_TYPE_SKILL_CALL,
)
from apps.tenant_app_service.agents.tools.scheduler import ScheduleTaskSchema


class TestScheduleTaskSchemaValidation:
    """Tests for ScheduleTaskSchema validation with task_type + task_config."""

    def test_agent_run_with_empty_config(self):
        """Test agent_run accepts empty task_config (auto-filled from runtime)."""
        schema = ScheduleTaskSchema(
            task_description="Test agent run",
            schedule_type="once",
            schedule_spec="+1h",
            task_type=TASK_TYPE_AGENT_RUN,
            task_config={},
        )

        assert schema.task_type == TASK_TYPE_AGENT_RUN
        assert schema.task_config == {}

    def test_skill_call_with_required_fields(self):
        """Test skill_call requires skill_id in task_config."""
        schema = ScheduleTaskSchema(
            task_description="Fetch weather",
            schedule_type="cron",
            schedule_spec="0 9 * * *",
            task_type=TASK_TYPE_SKILL_CALL,
            task_config={
                "skill_id": "weather-skill",
                "entrypoint": "skills.weather:run",
            },
        )

        assert schema.task_type == TASK_TYPE_SKILL_CALL
        assert schema.task_config["skill_id"] == "weather-skill"

    def test_skill_call_missing_skill_id_raises_error(self):
        """Test skill_call validation catches missing skill_id."""
        with pytest.raises(ValidationError) as exc_info:
            ScheduleTaskSchema(
                task_description="Call skill",
                schedule_type="once",
                schedule_spec="+1h",
                task_type=TASK_TYPE_SKILL_CALL,
                task_config={
                    "entrypoint": "skills.test:run",
                    # Missing: skill_id
                },
            )

        assert "skill_id" in str(exc_info.value).lower()

    def test_liveapp_job_with_all_required_fields(self):
        """Test liveapp_job accepts valid task_config."""
        schema = ScheduleTaskSchema(
            task_description="Run ETL",
            schedule_type="cron",
            schedule_spec="0 6 * * 1",
            task_type=TASK_TYPE_LIVEAPP_JOB,
            task_config={
                "app_id": 123,
                "job_name": "etl_pipeline",
                "entrypoint": "jobs/etl_pipeline.py",
                "environment": "prod",
            },
        )

        assert schema.task_type == TASK_TYPE_LIVEAPP_JOB
        assert schema.task_config["app_id"] == 123
        assert schema.task_config["environment"] == "prod"

    def test_liveapp_job_missing_entrypoint_raises_error(self):
        """Test liveapp_job validation catches missing entrypoint."""
        with pytest.raises(ValidationError) as exc_info:
            ScheduleTaskSchema(
                task_description="Run job",
                schedule_type="once",
                schedule_spec="+1h",
                task_type=TASK_TYPE_LIVEAPP_JOB,
                task_config={
                    "app_id": 123,
                    "job_name": "test_job",
                    # Missing: entrypoint
                },
            )

        assert "missing required keys" in str(exc_info.value).lower()
        assert "entrypoint" in str(exc_info.value).lower()

    def test_liveapp_job_missing_multiple_fields_raises_error(self):
        """Test liveapp_job validation reports all missing fields."""
        with pytest.raises(ValidationError) as exc_info:
            ScheduleTaskSchema(
                task_description="Run job",
                schedule_type="once",
                schedule_spec="+1h",
                task_type=TASK_TYPE_LIVEAPP_JOB,
                task_config={
                    # Missing: app_id, job_name, entrypoint
                },
            )

        error_msg = str(exc_info.value).lower()
        assert "missing required keys" in error_msg
        assert "app_id" in error_msg
        assert "job_name" in error_msg
        assert "entrypoint" in error_msg

    def test_invalid_task_type_raises_error(self):
        """Test that unsupported task_type is rejected (system tasks excluded)."""
        with pytest.raises(ValidationError) as exc_info:
            ScheduleTaskSchema(
                task_description="Invalid task",
                schedule_type="once",
                schedule_spec="+1h",
                task_type="invalid_type",
                task_config={},
            )

        error_msg = str(exc_info.value).lower()
        assert "task_type must be one of" in error_msg
        # System tasks should not be listed as available via agent tools
        assert "system" not in error_msg or "internally" in error_msg

    def test_agent_run_config_overrides_defaults(self):
        """Test that task_config can provide overrides for agent_run."""
        schema = ScheduleTaskSchema(
            task_description="Custom agent run",
            schedule_type="once",
            schedule_spec="+1h",
            task_type=TASK_TYPE_AGENT_RUN,
            task_config={
                "agent_id": 999,
                "origin_thread_id": "thread_abc",
            },
        )

        assert schema.task_config["agent_id"] == 999
        assert schema.task_config["origin_thread_id"] == "thread_abc"

    def test_liveapp_job_default_environment(self):
        """Test that environment defaults to 'prod' if not specified."""
        schema = ScheduleTaskSchema(
            task_description="Run job",
            schedule_type="once",
            schedule_spec="+1h",
            task_type=TASK_TYPE_LIVEAPP_JOB,
            task_config={
                "app_id": 123,
                "job_name": "test_job",
                "entrypoint": "jobs/test.py",
                # environment not specified - should default in implementation
            },
        )

        # Schema validation passes; default is applied in tool implementation
        assert "environment" not in schema.task_config
