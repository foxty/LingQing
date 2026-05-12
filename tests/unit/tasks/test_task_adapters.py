"""Unit tests for scheduled task adapters."""

from datetime import datetime, timezone
from types import SimpleNamespace

from apps.shared.tasks.adapters import db_task_to_domain
from apps.shared.tasks.domain import TASK_TYPE_LIVEAPP_JOB, TASK_TYPE_SKILL_CALL


class TestDbTaskToDomainAdapter:
    """Tests for db_task_to_domain adapter function."""

    def test_converts_basic_fields(self):
        """Test that basic fields are correctly mapped from DB to domain."""
        db_task = SimpleNamespace(
            id=1,
            tenant_id=7,
            user_id=42,
            name="test_task",
            task_type=TASK_TYPE_SKILL_CALL,
            task_config={"skill_id": "weather-skill"},
            schedule_type="cron",
            schedule_spec={"cron": "0 * * * *"},
            status="pending",
            next_run_at=datetime.now(timezone.utc),
            last_run_at=None,
            notification_channels=["email"],
            error_message=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        domain_task = db_task_to_domain(db_task)

        assert domain_task.id == 1
        assert domain_task.tenant_id == 7
        assert domain_task.user_id == 42
        assert domain_task.name == "test_task"
        assert domain_task.task_type == TASK_TYPE_SKILL_CALL
        assert domain_task.status == "pending"

    def test_handles_missing_optional_fields_with_defaults(self):
        """Test that missing optional fields get proper defaults."""
        db_task = SimpleNamespace(
            id=2,
            tenant_id=7,
            user_id=42,
            name="minimal_task",
            task_type=TASK_TYPE_LIVEAPP_JOB,
            # Missing: task_config, schedule_spec, next_run_at, etc.
            schedule_type="once",
            status="pending",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        domain_task = db_task_to_domain(db_task)

        # Should use defaults for missing fields
        assert domain_task.task_config == {}
        assert domain_task.schedule_spec == {}
        assert domain_task.next_run_at is None
        assert domain_task.last_run_at is None
        assert domain_task.notification_channels is None
        assert domain_task.error_message is None

    def test_preserves_liveapp_job_config(self):
        """Test that liveapp_job task_config is preserved correctly."""
        db_task = SimpleNamespace(
            id=3,
            tenant_id=7,
            user_id=42,
            name="etl_job",
            task_type=TASK_TYPE_LIVEAPP_JOB,
            task_config={
                "app_id": 123,
                "job_name": "sync_weather",
                "entrypoint": "jobs/sync_weather.py",
                "environment": "prod",
            },
            schedule_type="cron",
            schedule_spec={"cron": "0 6 * * *"},
            status="pending",
            next_run_at=None,
            last_run_at=None,
            notification_channels=None,
            error_message=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        domain_task = db_task_to_domain(db_task)

        assert domain_task.task_type == TASK_TYPE_LIVEAPP_JOB
        assert domain_task.task_config["app_id"] == 123
        assert domain_task.task_config["job_name"] == "sync_weather"
        assert domain_task.task_config["entrypoint"] == "jobs/sync_weather.py"

    def test_domain_model_has_business_methods(self):
        """Test that converted domain model has business logic methods."""
        db_task = SimpleNamespace(
            id=4,
            tenant_id=7,
            user_id=42,
            name="skill_task",
            task_type=TASK_TYPE_SKILL_CALL,
            task_config={
                "skill_id": "weather-skill",
                "entrypoint": "skills.weather:run",
            },
            schedule_type="once",
            schedule_spec={},
            status="pending",
            next_run_at=None,
            last_run_at=None,
            notification_channels=None,
            error_message=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        domain_task = db_task_to_domain(db_task)

        # Domain model should have business logic methods
        assert hasattr(domain_task, "get_sandbox_execution_params")

        params = domain_task.get_sandbox_execution_params()
        assert params is not None
        assert params.target_id == "weather-skill"
        assert "python -m" in params.command_template

    def test_returns_none_for_internal_tasks(self):
        """Test that internal tasks (agent_run, system) return None sandbox params."""
        for task_type in ["agent_run", "system"]:
            db_task = SimpleNamespace(
                id=5,
                tenant_id=7,
                user_id=42,
                name=f"{task_type}_task",
                task_type=task_type,
                task_config={},
                schedule_type="once",
                schedule_spec={},
                status="pending",
                next_run_at=None,
                last_run_at=None,
                notification_channels=None,
                error_message=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

            domain_task = db_task_to_domain(db_task)
            params = domain_task.get_sandbox_execution_params()

            assert params is None, f"Internal task type {task_type} should return None"

    def test_adapter_maintains_clean_architecture(self):
        """Test that adapter properly separates DB and domain concerns."""
        # This test verifies the architectural boundary
        db_task = SimpleNamespace(
            id=6,
            tenant_id=7,
            user_id=42,
            name="test",
            task_type=TASK_TYPE_LIVEAPP_JOB,
            task_config={"app_id": 1},
            schedule_type="once",
            schedule_spec={},
            status="pending",
            next_run_at=None,
            last_run_at=None,
            notification_channels=None,
            error_message=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        # Adapter converts DB model → Domain model
        domain_task = db_task_to_domain(db_task)

        # Domain model should be a proper dataclass with methods
        assert type(domain_task).__name__ == "ScheduledTaskDomain"
        assert hasattr(domain_task, "get_sandbox_execution_params")

        # DB model should NOT have domain methods
        assert not hasattr(db_task, "get_sandbox_execution_params")
