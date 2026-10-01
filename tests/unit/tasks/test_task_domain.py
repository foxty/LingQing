"""Unit tests for scheduled task domain models, constants, and business logic."""

from datetime import datetime, timezone

import pytest

from types import SimpleNamespace

from apps.shared.tasks.domain import (
    ALL_SCHEDULE_TYPES,
    ALL_SCHEDULED_TASK_TYPES,
    EXECUTION_MODE_INTERNAL,
    EXECUTION_MODE_SANDBOX,
    SCHEDULE_TYPE_CRON,
    SCHEDULE_TYPE_ONCE,
    TASK_RUN_STATUS_FAILED,
    TASK_RUN_STATUS_RUNNING,
    TASK_RUN_STATUS_SUCCESS,
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PAUSED,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_TYPE_AGENT_RUN,
    TASK_TYPE_LIVEAPP_JOB,
    TASK_TYPE_SKILL_CALL,
    TASK_TYPE_SYSTEM,
    ScheduledTaskDomain,
    is_system_scheduled_task,
    is_valid_schedule_type,
    is_valid_scheduled_task_type,
    normalize_agent_run_task_config,
    normalize_scheduled_task_name,
    parse_agent_run_task_config,
)


class TestConstants:
    """Verify all domain constants are defined correctly."""

    def test_task_type_constants(self):
        assert TASK_TYPE_AGENT_RUN == "agent_run"
        assert TASK_TYPE_SKILL_CALL == "skill_call"
        assert TASK_TYPE_LIVEAPP_JOB == "liveapp_job"
        assert TASK_TYPE_SYSTEM == "system"

    def test_all_task_types_tuple(self):
        assert set(ALL_SCHEDULED_TASK_TYPES) == {"agent_run", "skill_call", "liveapp_job", "system"}

    def test_execution_mode_constants(self):
        assert EXECUTION_MODE_INTERNAL == "internal"
        assert EXECUTION_MODE_SANDBOX == "sandbox"

    def test_schedule_type_constants(self):
        assert SCHEDULE_TYPE_ONCE == "once"
        assert SCHEDULE_TYPE_CRON == "cron"
        assert set(ALL_SCHEDULE_TYPES) == {"once", "cron"}

    def test_task_status_constants(self):
        assert TASK_STATUS_PENDING == "pending"
        assert TASK_STATUS_RUNNING == "running"
        assert TASK_STATUS_COMPLETED == "completed"
        assert TASK_STATUS_FAILED == "failed"
        assert TASK_STATUS_PAUSED == "paused"
        assert TASK_STATUS_CANCELLED == "cancelled"

    def test_task_run_status_constants(self):
        assert TASK_RUN_STATUS_RUNNING == "running"
        assert TASK_RUN_STATUS_SUCCESS == "success"
        assert TASK_RUN_STATUS_FAILED == "failed"


class TestNormalizeAgentRunTaskConfig:
    def test_strips_legacy_thread_mode(self):
        normalized = normalize_agent_run_task_config(
            {
                "agent_id": 1,
                "task_description": "daily sync",
                "thread_mode": "new",
            }
        )
        assert "thread_mode" not in normalized
        assert normalized["agent_id"] == 1


class TestIsValidScheduledTaskType:
    def test_valid_types(self):
        for t in ("agent_run", "skill_call", "liveapp_job", "system"):
            assert is_valid_scheduled_task_type(t) is True

    def test_invalid_types(self):
        for t in ("", "unknown", "etl_job", "AGENT_RUN", None):
            assert is_valid_scheduled_task_type(t) is False


class TestIsSystemScheduledTask:
    def test_true_when_stable_key_set(self):
        task = SimpleNamespace(stable_key="system.document_parse.poll")
        assert is_system_scheduled_task(task) is True

    def test_false_when_stable_key_missing(self):
        assert is_system_scheduled_task(SimpleNamespace(stable_key=None)) is False
        assert is_system_scheduled_task(SimpleNamespace()) is False

    def test_boundary_uses_stable_key_not_task_type(self):
        task = SimpleNamespace(stable_key=None, task_type=TASK_TYPE_SYSTEM)
        assert is_system_scheduled_task(task) is False


class TestIsValidScheduleType:
    def test_valid_types(self):
        assert is_valid_schedule_type("once") is True
        assert is_valid_schedule_type("cron") is True

    def test_invalid_types(self):
        for t in ("", "daily", "interval", "ONCE", None):
            assert is_valid_schedule_type(t) is False


class TestNormalizeScheduledTaskName:
    def test_strips_and_truncates(self):
        assert normalize_scheduled_task_name("  daily sync  ") == "daily sync"
        assert len(normalize_scheduled_task_name("x" * 200)) == 120

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="task name cannot be empty"):
            normalize_scheduled_task_name("   ")


class TestParseAgentRunTaskConfig:
    def test_valid_minimal_config(self):
        config = parse_agent_run_task_config(
            {
                "agent_id": 5,
                "task_description": "Run daily report",
            }
        )
        assert config["agent_id"] == 5
        assert config["task_description"] == "Run daily report"
        assert "origin_thread_id" not in config
        assert "thread_mode" not in config

    def test_valid_full_config(self):
        config = parse_agent_run_task_config(
            {
                "agent_id": 5,
                "task_description": "Run daily report",
                "origin_thread_id": "thread_123",
            }
        )
        assert config["agent_id"] == 5
        assert config["origin_thread_id"] == "thread_123"
        assert "thread_mode" not in config

    def test_legacy_thread_mode_is_ignored(self):
        config = parse_agent_run_task_config(
            {
                "agent_id": 5,
                "task_description": "Run daily report",
                "origin_thread_id": "thread_123",
                "thread_mode": "new",
            }
        )
        assert config["origin_thread_id"] == "thread_123"
        assert "thread_mode" not in config

    def test_missing_agent_id_raises(self):
        with pytest.raises(ValueError, match="agent_id is required"):
            parse_agent_run_task_config({"task_description": "test"})

    def test_invalid_agent_id_type_raises(self):
        with pytest.raises(ValueError, match="agent_id is required"):
            parse_agent_run_task_config({"agent_id": "not_int", "task_description": "test"})

    def test_missing_description_raises(self):
        with pytest.raises(ValueError, match="task_description is required"):
            parse_agent_run_task_config({"agent_id": 1})

    def test_empty_description_raises(self):
        with pytest.raises(ValueError, match="task_description is required"):
            parse_agent_run_task_config({"agent_id": 1, "task_description": "   "})

    def test_invalid_thread_mode_is_ignored(self):
        config = parse_agent_run_task_config(
            {
                "agent_id": 1,
                "task_description": "test",
                "thread_mode": "invalid_mode",
            }
        )
        assert "thread_mode" not in config


class TestGetSandboxExecutionParams:
    """Test ScheduledTaskDomain.get_sandbox_execution_params() for all task types."""

    @staticmethod
    def _make_task(task_type: str, task_config: dict) -> ScheduledTaskDomain:
        now = datetime.now(timezone.utc)
        return ScheduledTaskDomain(
            id=1,
            tenant_id=1,
            user_id=1,
            name="test_task",
            task_type=task_type,
            task_config=task_config,
            schedule_type="once",
            schedule_spec={"run_at": "2024-01-01T00:00:00Z"},
            status="pending",
            next_run_at=None,
            last_run_at=None,
            notification_channels=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )

    def test_skill_call_returns_params(self):
        task = self._make_task(
            TASK_TYPE_SKILL_CALL,
            {
                "skill_id": "weather-helper",
                "entrypoint": "skills.weather:run",
            },
        )
        params = task.get_sandbox_execution_params()
        assert params is not None
        assert params.target_id == "weather-helper"
        assert params.entrypoint == "skills.weather:run"
        assert params.command_template == "python -m skills.weather"

    def test_skill_call_without_colon_in_entrypoint(self):
        task = self._make_task(
            TASK_TYPE_SKILL_CALL,
            {
                "skill_id": "my-skill",
                "entrypoint": "skills.runner",
            },
        )
        params = task.get_sandbox_execution_params()
        assert params.command_template == "python -m skills.runner"

    def test_liveapp_job_returns_params(self):
        task = self._make_task(
            TASK_TYPE_LIVEAPP_JOB,
            {
                "app_id": 10,
                "job_name": "sync_data",
                "entrypoint": "jobs/sync_data.py",
            },
        )
        params = task.get_sandbox_execution_params()
        assert params is not None
        assert params.target_id == "10:sync_data"
        assert params.entrypoint == "jobs/sync_data.py"
        assert "cd /app_root" in params.command_template
        assert "python jobs/sync_data.py" in params.command_template

    def test_agent_run_returns_none(self):
        task = self._make_task(TASK_TYPE_AGENT_RUN, {"agent_id": 1})
        assert task.get_sandbox_execution_params() is None

    def test_system_returns_none(self):
        task = self._make_task(TASK_TYPE_SYSTEM, {"handler_ref": "mod:func"})
        assert task.get_sandbox_execution_params() is None

    def test_empty_task_config_handled_gracefully(self):
        task = self._make_task(TASK_TYPE_SKILL_CALL, {})
        params = task.get_sandbox_execution_params()
        assert params is not None
        assert params.target_id == ""
        assert params.entrypoint == ""


class TestScheduledTaskDomainCreation:
    def test_create_domain_model(self):
        now = datetime.now(timezone.utc)
        task = ScheduledTaskDomain(
            id=42,
            tenant_id=7,
            user_id=3,
            name="my_task",
            task_type=TASK_TYPE_LIVEAPP_JOB,
            task_config={"app_id": 1, "job_name": "j", "entrypoint": "j.py"},
            schedule_type=SCHEDULE_TYPE_CRON,
            schedule_spec={"cron": "0 * * * *"},
            status=TASK_STATUS_PENDING,
            next_run_at=now,
            last_run_at=None,
            notification_channels=["email"],
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        assert task.id == 42
        assert task.tenant_id == 7
        assert task.task_type == TASK_TYPE_LIVEAPP_JOB
        assert task.schedule_type == SCHEDULE_TYPE_CRON
        assert task.notification_channels == ["email"]

    def test_optional_fields_can_be_none(self):
        now = datetime.now(timezone.utc)
        task = ScheduledTaskDomain(
            id=1,
            tenant_id=1,
            user_id=1,
            name="t",
            task_type=TASK_TYPE_SYSTEM,
            task_config={},
            schedule_type=SCHEDULE_TYPE_ONCE,
            schedule_spec={},
            status=TASK_STATUS_RUNNING,
            next_run_at=None,
            last_run_at=None,
            notification_channels=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        assert task.next_run_at is None
        assert task.notification_channels is None
        assert task.error_message is None
