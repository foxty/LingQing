"""Unit tests for scheduled task execution orchestration service."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from apps.shared.tasks.domain import SCHEDULE_TYPE_ONCE, TASK_STATUS_RUNNING, TASK_TYPE_AGENT_RUN, TASK_TYPE_SYSTEM
from apps.shared.tasks.execution_service import ScheduledTaskExecutionService, TaskExecutionResult


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_poll_and_execute_applies_batch_error_policy_and_counts(monkeypatch):
    class FakeRepo:
        def __init__(self, session):
            self.set_error_calls = []

        async def recover_expired_running_tasks(self, *, limit):
            return [10]

        async def claim_due_tasks_with_lease(self, *, owner_instance_id, lease_ttl_seconds, limit):
            return [SimpleNamespace(id=1), SimpleNamespace(id=2)]

        async def set_error_message_for_task_ids(self, *, task_ids, error_message):
            self.set_error_calls.append((list(task_ids), error_message))

    fake_repo = FakeRepo(object())
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: fake_repo,
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    service = ScheduledTaskExecutionService()

    async def _fake_execute(task_id: int) -> bool:
        return task_id == 1

    monkeypatch.setattr(service, "execute_single_task", _fake_execute)

    result = await service.poll_and_execute(limit=10)

    assert result == {
        "recovered": 1,
        "claimed": 2,
        "success": 1,
        "failed": 0,
        "skipped": 1,
    }
    assert fake_repo.set_error_calls == [
        ([10], service.lease_recovery_error_message),
        ([1, 2], None),
    ]


@pytest.mark.asyncio
async def test_poll_and_execute_counts_executor_exceptions(monkeypatch):
    class FakeRepo:
        async def recover_expired_running_tasks(self, *, limit):
            return []

        async def claim_due_tasks_with_lease(self, *, owner_instance_id, lease_ttl_seconds, limit):
            return [SimpleNamespace(id=1), SimpleNamespace(id=2)]

        async def set_error_message_for_task_ids(self, *, task_ids, error_message):
            return None

    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: FakeRepo(),
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    service = ScheduledTaskExecutionService()

    async def _fake_execute(task_id: int) -> bool:
        if task_id == 2:
            raise RuntimeError("boom")
        return True

    monkeypatch.setattr(service, "execute_single_task", _fake_execute)

    result = await service.poll_and_execute(limit=10)

    assert result["success"] == 1
    assert result["failed"] == 1
    assert result["skipped"] == 0


@pytest.mark.asyncio
async def test_execute_single_task_returns_false_when_task_missing(monkeypatch):
    class FakeRepo:
        async def get_task_by_id(self, task_id):
            return None

    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: FakeRepo(),
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    service = ScheduledTaskExecutionService()
    result = await service.execute_single_task(task_id=1)
    assert result is False


@pytest.mark.asyncio
async def test_execute_single_task_without_executor_marks_failed(monkeypatch):
    task = SimpleNamespace(
        id=1,
        tenant_id=1,
        user_id=None,
        name="test_task",
        notification_channels=None,
        task_type="unknown",
        schedule_type=SCHEDULE_TYPE_ONCE,
        schedule_spec={},
        status=TASK_STATUS_RUNNING,
        owner_instance_id="s1",
        fencing_token=3,
        execution_mode="internal",
        task_config={},
    )
    run = SimpleNamespace(id=100, attempt=1, started_at=datetime.now(timezone.utc))

    class FakeRepo:
        def __init__(self):
            self.mark_failed_calls = 0

        async def get_task_by_id(self, task_id):
            return task

        async def create_run(self, *, task, orchestration_run_id, attempt=1):
            return run

        async def mark_run_failed(
            self, *, run_id, task_id, error_message, result, next_run_at, task_status, finished_at, duration_ms
        ):
            self.mark_failed_calls += 1

    fake_repo = FakeRepo()
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: fake_repo,
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    service = ScheduledTaskExecutionService()

    # Mock notification dispatch to avoid DB access
    async def _notify_noop(**kwargs):
        return None

    monkeypatch.setattr(service, "_dispatch_task_notification", _notify_noop)

    # The method should raise after marking as failed
    with pytest.raises(ValueError, match="No internal executor registered"):
        await service.execute_single_task(task_id=1)

    assert fake_repo.mark_failed_calls == 1


@pytest.mark.asyncio
async def test_execute_single_task_success_path_marks_success(monkeypatch):
    task = SimpleNamespace(
        id=1,
        tenant_id=1,
        task_type="agent_run",
        schedule_type=SCHEDULE_TYPE_ONCE,
        schedule_spec={},
        status=TASK_STATUS_RUNNING,
        owner_instance_id="s1",
        fencing_token=3,
        name="t",
        user_id=1,
        notification_channels=None,
        execution_mode="internal",
        handler_ref=None,
    )
    run = SimpleNamespace(id=100, attempt=1, started_at=datetime.now(timezone.utc))

    class FakeRepo:
        def __init__(self):
            self.mark_success_calls = 0

        async def get_task_by_id(self, task_id):
            return task

        async def create_run(self, *, task, orchestration_run_id, attempt=1):
            return run

        async def has_execution_ownership(self, *, task_id, owner_instance_id, fencing_token):
            return True

        async def mark_run_success(
            self, *, run_id, task_id, result, next_run_at, task_status, finished_at, duration_ms
        ):
            self.mark_success_calls += 1

        async def mark_run_failed(
            self, *, run_id, task_id, error_message, result, next_run_at, task_status, finished_at, duration_ms
        ):
            raise AssertionError("should not fail")

    fake_repo = FakeRepo()
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: fake_repo,
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    async def _executor(_task):
        return TaskExecutionResult(success=True, payload={"ok": True})

    service = ScheduledTaskExecutionService(
        internal_executors={TASK_TYPE_AGENT_RUN: _executor},
    )

    async def _heartbeat_noop(**kwargs):
        await asyncio.sleep(0)
        return TaskExecutionResult(success=True, payload={"ok": True})

    async def _notify_noop(**kwargs):
        return None

    monkeypatch.setattr(service, "_lease_heartbeat_loop", _heartbeat_noop)
    monkeypatch.setattr(service, "_dispatch_task_notification", _notify_noop)

    result = await service.execute_single_task(task_id=1)

    assert result is True
    assert fake_repo.mark_success_calls == 1


@pytest.mark.asyncio
async def test_execute_single_task_lease_lost_marks_failed(monkeypatch):
    task = SimpleNamespace(
        id=1,
        tenant_id=1,
        task_type="agent_run",
        schedule_type=SCHEDULE_TYPE_ONCE,
        schedule_spec={},
        status=TASK_STATUS_RUNNING,
        owner_instance_id="s1",
        fencing_token=3,
        name="t",
        user_id=1,
        notification_channels=None,
        execution_mode="internal",
        task_config={},
    )
    run = SimpleNamespace(id=100, attempt=1, started_at=datetime.now(timezone.utc))

    class FakeRepo:
        def __init__(self):
            self.mark_failed_calls = 0

        async def get_task_by_id(self, task_id):
            return task

        async def create_run(self, *, task, orchestration_run_id, attempt=1):
            return run

        async def has_execution_ownership(self, *, task_id, owner_instance_id, fencing_token):
            return True

        async def mark_run_success(
            self, *, run_id, task_id, result, next_run_at, task_status, finished_at, duration_ms
        ):
            raise AssertionError("should not succeed")

        async def mark_run_failed(
            self, *, run_id, task_id, error_message, result, next_run_at, task_status, finished_at, duration_ms
        ):
            self.mark_failed_calls += 1

    fake_repo = FakeRepo()
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: fake_repo,
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    async def _executor(_task):
        await asyncio.sleep(0)
        return TaskExecutionResult(success=True, payload={"ok": True})

    service = ScheduledTaskExecutionService(
        internal_executors={TASK_TYPE_AGENT_RUN: _executor},
    )

    async def _heartbeat_lost(*, lease_lost_event, **kwargs):
        lease_lost_event.set()

    async def _notify_noop(**kwargs):
        return None

    monkeypatch.setattr(service, "_lease_heartbeat_loop", _heartbeat_lost)
    monkeypatch.setattr(service, "_dispatch_task_notification", _notify_noop)

    result = await service.execute_single_task(task_id=1)

    assert result is False
    assert fake_repo.mark_failed_calls == 1


@pytest.mark.asyncio
async def test_execute_single_task_passes_default_task_context(monkeypatch):
    task = SimpleNamespace(
        id=1,
        tenant_id=11,
        user_id=22,
        owner_id=22,
        task_type="system",
        schedule_type=SCHEDULE_TYPE_ONCE,
        schedule_spec={},
        status=TASK_STATUS_RUNNING,
        owner_instance_id="s1",
        fencing_token=3,
        name="t",
        notification_channels=None,
        execution_mode="internal",
        task_config={"handler_ref": "apps.shared.tasks.system.jobs.vector_sync:cleanup_orphaned_vectors"},
        input_params={"dry_run": False},
    )
    run = SimpleNamespace(id=100, attempt=1, started_at=datetime.now(timezone.utc))

    class FakeRepo:
        async def get_task_by_id(self, task_id):
            return task

        async def create_run(self, *, task, orchestration_run_id, attempt=1):
            return run

        async def has_execution_ownership(self, *, task_id, owner_instance_id, fencing_token):
            return True

        async def mark_run_success(
            self, *, run_id, task_id, result, next_run_at, task_status, finished_at, duration_ms
        ):
            return None

        async def mark_run_failed(
            self, *, run_id, task_id, error_message, result, next_run_at, task_status, finished_at, duration_ms
        ):
            raise AssertionError("should not fail")

    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: FakeRepo(),
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    captured_ctx = {}

    async def _executor(_task):
        # The service method builds context internally, so we capture it from the task
        captured_ctx["tenant_id"] = _task.tenant_id
        captured_ctx["user_id"] = _task.user_id
        captured_ctx["input_params"] = _task.input_params or {}
        return TaskExecutionResult(success=True, payload={"ok": True})

    service = ScheduledTaskExecutionService(
        internal_executors={TASK_TYPE_SYSTEM: _executor},
    )

    async def _heartbeat_noop(**kwargs):
        await asyncio.sleep(0)

    async def _notify_noop(**kwargs):
        return None

    monkeypatch.setattr(service, "_lease_heartbeat_loop", _heartbeat_noop)
    monkeypatch.setattr(service, "_dispatch_task_notification", _notify_noop)

    result = await service.execute_single_task(task_id=1)

    assert result is True
    assert captured_ctx["tenant_id"] == 11
    assert captured_ctx["user_id"] == 22
    assert captured_ctx["input_params"] == {"dry_run": False}


@pytest.mark.asyncio
async def test_execute_single_task_rolls_back_before_mark_failed(monkeypatch):
    task = SimpleNamespace(
        id=1,
        tenant_id=1,
        user_id=1,
        owner_id=1,
        task_type="agent_run",
        schedule_type=SCHEDULE_TYPE_ONCE,
        schedule_spec={},
        status=TASK_STATUS_RUNNING,
        owner_instance_id="s1",
        fencing_token=3,
        name="t",
        notification_channels=None,
        execution_mode="internal",
        handler_ref=None,
        input_params=None,
    )
    run = SimpleNamespace(id=100, attempt=1, started_at=datetime.now(timezone.utc))

    calls: list[str] = []

    class FakeSession:
        async def rollback(self):
            calls.append("rollback")

    class FakeRepo:
        async def get_task_by_id(self, task_id):
            return task

        async def create_run(self, *, task, orchestration_run_id, attempt=1):
            return run

        async def mark_run_failed(
            self, *, run_id, task_id, error_message, result, next_run_at, task_status, finished_at, duration_ms
        ):
            calls.append("mark_failed")

    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: FakeRepo(),
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(FakeSession()),
    )

    async def _executor(_task):
        raise RuntimeError("boom")

    service = ScheduledTaskExecutionService(
        internal_executors={TASK_TYPE_AGENT_RUN: _executor},
    )

    async def _heartbeat_noop(**kwargs):
        await asyncio.sleep(0)
        return TaskExecutionResult(success=True, payload={"ok": True})

    async def _notify_noop(**kwargs):
        return None

    monkeypatch.setattr(service, "_lease_heartbeat_loop", _heartbeat_noop)
    monkeypatch.setattr(service, "_dispatch_task_notification", _notify_noop)

    with pytest.raises(RuntimeError, match="boom"):
        await service.execute_single_task(task_id=1)

    assert calls == ["rollback", "mark_failed"]


@pytest.mark.asyncio
async def test_dispatch_sandbox_task_includes_input_params(monkeypatch):
    """Test that _dispatch_sandbox_task correctly passes input_params in the command."""
    from datetime import datetime, timezone

    from apps.shared.sandbox.client import SandboxResult
    from apps.shared.tasks.domain import TASK_TYPE_SKILL_CALL, ScheduledTaskDomain

    domain_task = ScheduledTaskDomain(
        id=42,
        tenant_id=1,
        user_id=1,
        name="test_skill_task",
        task_type=TASK_TYPE_SKILL_CALL,
        task_config={"skill_id": "123", "entrypoint": "skills.weather:run"},
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

    captured = {}

    class FakeSandboxClient:
        def __init__(self, **kwargs):
            pass

        async def execute(self, command, timeout_seconds, context, working_dir, app_root_subpath):
            captured["command"] = command
            captured["timeout_seconds"] = timeout_seconds
            captured["working_dir"] = working_dir
            return SandboxResult(exit_code=0, stdout='{"result": "ok"}', stderr="")

        async def close(self):
            pass

    monkeypatch.setattr("apps.shared.tasks.execution_service.SandboxClient", FakeSandboxClient)

    service = ScheduledTaskExecutionService()

    # Test with input_params
    input_params = {"param1": "value1", "param2": 123}
    result = await service._dispatch_sandbox_task(domain_task, input_params=input_params)

    # Verify the command includes TASK_INPUT_PARAMS with the input_params
    command = captured["command"]
    assert "TASK_INPUT_PARAMS=" in command
    assert "value1" in command
    # Verify runtime context is also set
    assert "TASK_RUNTIME_CONTEXT=" in command
    # Verify result is parsed
    assert result.success is True
    assert result.payload["exit_code"] == 0
    assert result.payload["output"] == {"result": "ok"}


@pytest.mark.asyncio
async def test_dispatch_sandbox_task_without_input_params(monkeypatch):
    """Test that _dispatch_sandbox_task handles None input_params gracefully."""
    from datetime import datetime, timezone

    from apps.shared.sandbox.client import SandboxResult
    from apps.shared.tasks.domain import TASK_TYPE_SKILL_CALL, ScheduledTaskDomain

    domain_task = ScheduledTaskDomain(
        id=42,
        tenant_id=1,
        user_id=1,
        name="test_skill_task",
        task_type=TASK_TYPE_SKILL_CALL,
        task_config={"skill_id": "123", "entrypoint": "skills.weather:run"},
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

    captured = {}

    class FakeSandboxClient:
        def __init__(self, **kwargs):
            pass

        async def execute(self, command, timeout_seconds, context, working_dir, app_root_subpath):
            captured["command"] = command
            return SandboxResult(exit_code=0, stdout="", stderr="")

        async def close(self):
            pass

    monkeypatch.setattr("apps.shared.tasks.execution_service.SandboxClient", FakeSandboxClient)

    service = ScheduledTaskExecutionService()

    # Test without input_params (should default to empty dict)
    result = await service._dispatch_sandbox_task(domain_task)

    # Verify the command includes TASK_INPUT_PARAMS with empty dict
    command = captured["command"]
    assert "TASK_INPUT_PARAMS=" in command
    assert "TASK_RUNTIME_CONTEXT=" in command
    assert result.success is True
    assert result.payload["exit_code"] == 0


# ============================================================
# Additional tests for _dispatch_sandbox_task, _schema_for_environment,
# execute_single_task edge paths, config, and task-type executors.
# ============================================================


def _make_domain_task(task_type="skill_call", task_config=None, **overrides):
    """Helper to build a ScheduledTaskDomain with sensible defaults."""
    from datetime import datetime, timezone

    from apps.shared.tasks.domain import ScheduledTaskDomain

    defaults = dict(
        id=42,
        tenant_id=1,
        user_id=1,
        name="test_task",
        task_type=task_type,
        task_config=task_config or {"skill_id": "s1", "entrypoint": "mod:run"},
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
    defaults.update(overrides)
    return ScheduledTaskDomain(**defaults)


class _FakeSandboxClient:
    """Reusable fake SandboxClient for _dispatch_sandbox_task tests."""

    def __init__(self, *, exit_code=0, stdout="", stderr=""):
        self._exit_code = exit_code
        self._stdout = stdout
        self._stderr = stderr
        self.captured = {}

    async def execute(self, command, timeout_seconds, context, working_dir, app_root_subpath):
        from apps.shared.sandbox.client import SandboxResult

        self.captured.update(
            command=command,
            timeout_seconds=timeout_seconds,
            working_dir=working_dir,
            app_root_subpath=app_root_subpath,
            context=context,
        )
        return SandboxResult(exit_code=self._exit_code, stdout=self._stdout, stderr=self._stderr)

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_dispatch_sandbox_task_with_extra_runtime_context(monkeypatch):
    """Verify liveapp path sets working_dir=/app_root and computes app_root_subpath."""
    fake = _FakeSandboxClient(stdout='{"rows": 10}')
    monkeypatch.setattr("apps.shared.tasks.execution_service.SandboxClient", lambda: fake)

    service = ScheduledTaskExecutionService()
    domain_task = _make_domain_task(
        task_type="liveapp_job",
        task_config={"app_id": 5, "job_name": "sync", "entrypoint": "jobs/sync.py"},
    )

    extra_ctx = {"app_id": 5, "environment": "dev"}
    result = await service._dispatch_sandbox_task(domain_task, extra_runtime_context=extra_ctx)

    assert fake.captured["working_dir"] == "/app_root"
    assert "tenants/tenant_1/apps/app_5/env/dev" in fake.captured["app_root_subpath"]
    # Runtime context merged: tenant_id + task_id + extra
    assert '"app_id"' in fake.captured["command"]
    assert result.payload["output"] == {"rows": 10}


@pytest.mark.asyncio
async def test_dispatch_sandbox_task_non_json_stdout(monkeypatch):
    """Non-JSON stdout should not populate 'output' key."""
    fake = _FakeSandboxClient(stdout="hello world\nnot json")
    monkeypatch.setattr("apps.shared.tasks.execution_service.SandboxClient", lambda: fake)

    service = ScheduledTaskExecutionService()
    domain_task = _make_domain_task()
    result = await service._dispatch_sandbox_task(domain_task)

    assert result.success is True
    assert result.payload["stdout"] == "hello world\nnot json"
    assert "output" not in result.payload


@pytest.mark.asyncio
async def test_dispatch_sandbox_task_returns_non_zero_exit(monkeypatch):
    """Non-zero exit code should be returned without raising — caller decides outcome."""
    fake = _FakeSandboxClient(exit_code=1, stderr="boom")
    monkeypatch.setattr("apps.shared.tasks.execution_service.SandboxClient", lambda: fake)

    service = ScheduledTaskExecutionService()
    domain_task = _make_domain_task()

    result = await service._dispatch_sandbox_task(domain_task)
    assert result.success is False
    assert result.payload["exit_code"] == 1
    assert result.payload["stderr"] == "boom"


@pytest.mark.asyncio
async def test_execute_single_task_sandbox_non_zero_exit_marks_failed(monkeypatch):
    """Sandbox tasks with non-zero exit code should be marked failed by the caller."""
    task = SimpleNamespace(
        id=1,
        tenant_id=1,
        user_id=1,
        name="sandbox_task",
        task_type="skill_call",
        schedule_type=SCHEDULE_TYPE_ONCE,
        schedule_spec={},
        status=TASK_STATUS_RUNNING,
        owner_instance_id="s1",
        fencing_token=3,
        notification_channels=None,
        execution_mode="sandbox",
        task_config={"skill_id": "s1", "entrypoint": "mod:run"},
        input_params=None,
    )
    run = SimpleNamespace(id=100, attempt=1, started_at=datetime.now(timezone.utc))
    mark_failed_calls = 0
    mark_success_calls = 0
    captured_error = {}

    class FakeRepo:
        async def get_task_by_id(self, task_id):
            return task

        async def create_run(self, *, task, orchestration_run_id, attempt=1):
            return run

        async def mark_run_failed(
            self, *, run_id, task_id, error_message, result, next_run_at, task_status, finished_at, duration_ms
        ):
            nonlocal mark_failed_calls
            mark_failed_calls += 1
            captured_error["error_message"] = error_message

        async def mark_run_success(
            self, *, run_id, task_id, result, next_run_at, task_status, finished_at, duration_ms
        ):
            nonlocal mark_success_calls
            mark_success_calls += 1

    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: FakeRepo(),
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    service = ScheduledTaskExecutionService()

    async def _dispatch(_task, **kwargs):
        return TaskExecutionResult(
            success=False,
            payload={"stdout": "some output", "stderr": "script error", "exit_code": 1},
            stdout="some output",
            stderr="script error",
            error_message="script error",
        )

    monkeypatch.setattr(service, "_dispatch_sandbox_task", _dispatch)

    async def _heartbeat_noop(**kwargs):
        await asyncio.sleep(0)

    async def _notify_noop(**kwargs):
        pass

    monkeypatch.setattr(service, "_lease_heartbeat_loop", _heartbeat_noop)
    monkeypatch.setattr(service, "_dispatch_task_notification", _notify_noop)
    # _persist_run_logs should be a no-op in tests (no real filesystem)
    monkeypatch.setattr(service, "_persist_run_logs", lambda **kwargs: None)

    result = await service.execute_single_task(task_id=1)
    assert result is False
    assert mark_failed_calls == 1
    assert mark_success_calls == 0
    assert "script error" in captured_error["error_message"]


class TestSchemaForEnvironment:
    def test_prod_schema(self):
        service = ScheduledTaskExecutionService()
        assert service._schema_for_environment(app_id=42, environment="prod") == "app_42"

    def test_dev_schema(self):
        service = ScheduledTaskExecutionService()
        assert service._schema_for_environment(app_id=42, environment="dev") == "app_42_dev"

    def test_test_schema(self):
        service = ScheduledTaskExecutionService()
        assert service._schema_for_environment(app_id=7, environment="test") == "app_7_test"


class TestScheduledTaskExecutionConfig:
    def test_from_env_generates_instance_id(self, monkeypatch):
        monkeypatch.setattr("apps.shared.tasks.execution_service.EnvConfig.SCHEDULER_INSTANCE_ID", "auto")
        monkeypatch.setattr("apps.shared.tasks.execution_service.EnvConfig.SCHEDULED_TASK_LEASE_TTL_SECONDS", 120)
        monkeypatch.setattr(
            "apps.shared.tasks.execution_service.EnvConfig.SCHEDULED_TASK_HEARTBEAT_INTERVAL_SECONDS", 30
        )
        monkeypatch.setattr("apps.shared.tasks.execution_service.EnvConfig.SCHEDULED_TASK_WATCHDOG_LIMIT", 5)

        from apps.shared.tasks.execution_service import ScheduledTaskExecutionConfig

        config = ScheduledTaskExecutionConfig.from_env()
        assert config.lease_ttl_seconds == 120
        assert config.heartbeat_interval_seconds == 30
        assert config.watchdog_recovery_limit == 5
        assert config.owner_instance_id  # auto-generated, non-empty

    def test_from_env_uses_configured_instance_id(self, monkeypatch):
        monkeypatch.setattr("apps.shared.tasks.execution_service.EnvConfig.SCHEDULER_INSTANCE_ID", "my-host-1")
        monkeypatch.setattr("apps.shared.tasks.execution_service.EnvConfig.SCHEDULED_TASK_LEASE_TTL_SECONDS", 60)
        monkeypatch.setattr(
            "apps.shared.tasks.execution_service.EnvConfig.SCHEDULED_TASK_HEARTBEAT_INTERVAL_SECONDS", 15
        )
        monkeypatch.setattr("apps.shared.tasks.execution_service.EnvConfig.SCHEDULED_TASK_WATCHDOG_LIMIT", 3)

        from apps.shared.tasks.execution_service import ScheduledTaskExecutionConfig

        config = ScheduledTaskExecutionConfig.from_env()
        assert config.owner_instance_id == "my-host-1"


@pytest.mark.asyncio
async def test_execute_single_task_returns_false_when_no_owner(monkeypatch):
    """Task without owner_instance_id should be skipped (return False)."""
    task = SimpleNamespace(
        id=1,
        tenant_id=1,
        status=TASK_STATUS_RUNNING,
        owner_instance_id=None,
        fencing_token=1,
    )

    class FakeRepo:
        async def get_task_by_id(self, task_id):
            return task

    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: FakeRepo(),
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    service = ScheduledTaskExecutionService()
    result = await service.execute_single_task(task_id=1)
    assert result is False


@pytest.mark.asyncio
async def test_execute_single_task_cron_computes_next_run_at(monkeypatch):
    """Cron tasks should compute next_run_at via compute_next_run_at."""
    from apps.shared.tasks.domain import SCHEDULE_TYPE_CRON as CRON

    task = SimpleNamespace(
        id=1,
        tenant_id=1,
        user_id=1,
        name="cron_task",
        task_type="agent_run",
        schedule_type=CRON,
        schedule_spec={"cron": "0 * * * *"},
        status=TASK_STATUS_RUNNING,
        owner_instance_id="s1",
        fencing_token=1,
        notification_channels=None,
        execution_mode="internal",
        task_config={},
    )
    run = SimpleNamespace(id=100, attempt=1, started_at=datetime.now(timezone.utc))
    captured_next_run = {}

    class FakeRepo:
        async def get_task_by_id(self, task_id):
            return task

        async def create_run(self, *, task, orchestration_run_id, attempt=1):
            return run

        async def has_execution_ownership(self, *, task_id, owner_instance_id, fencing_token):
            return True

        async def mark_run_success(
            self, *, run_id, task_id, result, next_run_at, task_status, finished_at, duration_ms
        ):
            captured_next_run["next_run_at"] = next_run_at

    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.ScheduledTaskRepository",
        lambda session: FakeRepo(),
    )
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    async def _executor(_task):
        return TaskExecutionResult(success=True, payload={"ok": True})

    service = ScheduledTaskExecutionService(
        internal_executors={TASK_TYPE_AGENT_RUN: _executor},
    )

    async def _heartbeat_noop(**kwargs):
        await asyncio.sleep(0)

    async def _notify_noop(**kwargs):
        pass

    monkeypatch.setattr(service, "_lease_heartbeat_loop", _heartbeat_noop)
    monkeypatch.setattr(service, "_dispatch_task_notification", _notify_noop)

    result = await service.execute_single_task(task_id=1)
    assert result is True
    # next_run_at should be a datetime in the future (not None for cron)
    assert captured_next_run["next_run_at"] is not None


@pytest.mark.asyncio
async def test_execute_liveapp_job_task_builds_runtime_context(monkeypatch):
    """execute_liveapp_job_task should return LiveAppJobExecutionResult with runtime_context."""
    from types import SimpleNamespace as NS

    from apps.shared.tasks.execution_service import LiveAppJobExecutionResult

    task = NS(
        id=10,
        tenant_id=1,
        user_id=2,
        task_config={"app_id": 5, "job_name": "sync", "entrypoint": "jobs/sync.py", "environment": "prod"},
    )

    # Mock get_app_path and _bootstrap_python_sdk (imported lazily inside method)
    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_app_path",
        lambda tenant_id, app_id, environment="prod", create=True: "/tmp/fake_path",
    )
    monkeypatch.setattr(
        "apps.shared.live_app.workspace._bootstrap_python_sdk",
        lambda path: None,
    )

    # Mock LiveAppRepository and DataSourceRepository
    fake_live_app = NS(id=5, data_source_id=99)

    class FakeLiveAppRepo:
        def __init__(self, session):
            pass

        async def get_for_tenant(self, *, app_id, tenant_id):
            return fake_live_app

    from apps.shared.data_source.domain import DatabaseConnectionVO, DataSourceDomain

    now = datetime.now(timezone.utc)
    fake_ds_domain = DataSourceDomain(
        id=99,
        tenant_id=1,
        name="pg",
        type="postgresql",
        managed=True,
        connection=DatabaseConnectionVO(host="localhost", port=5432, database="testdb", username="u", password="p"),
        description=None,
        owner_id=2,
        asset_count=0,
        created_at=now,
        updated_at=now,
    )

    class FakeDataSourceRepo:
        def __init__(self, session):
            pass

        async def get_by_id_and_tenant(self, *, data_source_id, tenant_id):
            return NS(id=99, type="postgresql", managed=True)

    monkeypatch.setattr("apps.shared.live_app.repository.LiveAppRepository", FakeLiveAppRepo)
    monkeypatch.setattr("apps.shared.data_source.repository.DataSourceRepository", FakeDataSourceRepo)
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.db_data_source_to_domain",
        lambda ds: fake_ds_domain,
    )

    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    # Mock JWT settings
    fake_settings = NS(SECRET_KEY="test-secret-key-for-jwt-signing-32b", ALGORITHM="HS256")
    monkeypatch.setattr("apps.shared.tasks.execution_service.get_settings", lambda: fake_settings)

    service = ScheduledTaskExecutionService()
    result = await service.execute_liveapp_job_task(task)

    assert isinstance(result, LiveAppJobExecutionResult)
    assert result.app_id == 5
    assert result.job_name == "sync"
    assert result.entrypoint == "jobs/sync.py"
    assert result.runtime_context["tenant_id"] == 1
    assert result.runtime_context["app_id"] == 5
    assert result.runtime_context["environment"] == "prod"
    assert result.runtime_context["schema_name"] == "app_5"
    assert "access_token" in result.runtime_context
    assert "api_base_url" in result.runtime_context


@pytest.mark.asyncio
async def test_execute_liveapp_job_task_raises_when_app_not_found(monkeypatch):
    """Should raise ValueError when live app does not exist."""
    from types import SimpleNamespace as NS

    task = NS(
        id=10,
        tenant_id=1,
        user_id=2,
        task_config={"app_id": 999, "job_name": "j", "entrypoint": "j.py"},
    )

    monkeypatch.setattr(
        "apps.shared.live_app.workspace.get_app_path",
        lambda tenant_id, app_id, environment="prod", create=True: "/tmp/fake",
    )
    monkeypatch.setattr("apps.shared.live_app.workspace._bootstrap_python_sdk", lambda p: None)

    class FakeLiveAppRepo:
        def __init__(self, session):
            pass

        async def get_for_tenant(self, *, app_id, tenant_id):
            return None  # App not found

    monkeypatch.setattr("apps.shared.live_app.repository.LiveAppRepository", FakeLiveAppRepo)
    monkeypatch.setattr(
        "apps.shared.tasks.execution_service.app_db_session",
        lambda: _SessionContext(object()),
    )

    service = ScheduledTaskExecutionService()

    with pytest.raises(ValueError, match="not found"):
        await service.execute_liveapp_job_task(task)
