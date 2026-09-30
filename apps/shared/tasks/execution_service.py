"""Scheduled task execution orchestration service."""

import asyncio
import json
import os
import shlex
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import jwt

from apps.config import EnvConfig, get_settings
from apps.shared.data_source.adapters import db_data_source_to_domain
from apps.shared.db.models import ScheduledTask, TaskRun
from apps.shared.db.session import app_db_session
from apps.shared.notification import NotificationEvent, NotificationService
from apps.shared.sandbox.client import SandboxClient, SandboxExecutionContext
from apps.shared.tasks.adapters import db_task_to_domain
from apps.shared.tasks.domain import (
    EXECUTION_MODE_SANDBOX,
    SCHEDULE_TYPE_CRON,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_TYPE_LIVEAPP_JOB,
    TASK_TYPE_SYSTEM,
    LiveAppJobTaskConfig,
    ScheduledTaskDomain,
    TaskExecutionContext,
)
from apps.shared.tasks.repository import ScheduledTaskRepository
from apps.shared.tasks.run_log_writer import RunLogPaths, RunLogWriter
from apps.shared.tasks.scheduling import compute_next_run_at
from apps.shared.tasks.system.handler_result import SystemTaskHandlerResult
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TaskExecutionResult:
    """Normalized result from any task executor — sandbox or internal.

    Each executor (sandbox, agent_run, system) produces this envelope.
    The orchestration layer (execute_single_task) only inspects these fields,
    never the raw executor-specific output.
    """

    success: bool
    payload: dict[str, Any]  # What goes into DB run.result
    stdout: str = ""  # Sandbox: raw stdout; internal: ""
    stderr: str = ""  # Sandbox: raw stderr; internal: ""
    error_message: str | None = None  # Human-readable failure reason


InternalTaskExecutor = Callable[[ScheduledTaskDomain], Awaitable["TaskExecutionResult"]]


@dataclass
class LiveAppJobExecutionResult:
    """Result of preparing a liveapp job for sandbox execution."""

    app_id: int
    job_name: str
    entrypoint: str
    runtime_context: dict[str, Any]

    @property
    def status(self) -> str:
        """Execution status (always sandbox_execution_pending for this result type)."""
        return "sandbox_execution_pending"


LEASE_RECOVERY_ERROR_MESSAGE = "Recovered after lease timeout"


class SandboxExecutionError(Exception):
    """Raised when sandbox execution returns a non-zero exit code or HTTP error."""


@dataclass(frozen=True)
class ScheduledTaskExecutionConfig:
    owner_instance_id: str
    lease_ttl_seconds: int
    heartbeat_interval_seconds: int
    watchdog_recovery_limit: int
    lease_recovery_error_message: str

    @classmethod
    def from_env(cls) -> "ScheduledTaskExecutionConfig":
        configured_instance_id = EnvConfig.SCHEDULER_INSTANCE_ID.strip()
        owner_instance_id = configured_instance_id
        if not configured_instance_id or configured_instance_id.lower() == "auto":
            owner_instance_id = f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
        return cls(
            owner_instance_id=owner_instance_id,
            lease_ttl_seconds=EnvConfig.SCHEDULED_TASK_LEASE_TTL_SECONDS,
            heartbeat_interval_seconds=EnvConfig.SCHEDULED_TASK_HEARTBEAT_INTERVAL_SECONDS,
            watchdog_recovery_limit=EnvConfig.SCHEDULED_TASK_WATCHDOG_LIMIT,
            lease_recovery_error_message=LEASE_RECOVERY_ERROR_MESSAGE,
        )


class ScheduledTaskExecutionService:
    """Orchestrates polling, lease maintenance, and execution for scheduled tasks."""

    def __init__(
        self,
        *,
        config: ScheduledTaskExecutionConfig | None = None,
        internal_executors: dict[str, InternalTaskExecutor] | None = None,
    ):
        runtime_config = config or ScheduledTaskExecutionConfig.from_env()
        self.owner_instance_id = runtime_config.owner_instance_id
        self.lease_ttl_seconds = runtime_config.lease_ttl_seconds
        self.heartbeat_interval_seconds = runtime_config.heartbeat_interval_seconds
        self.watchdog_recovery_limit = runtime_config.watchdog_recovery_limit
        self.lease_recovery_error_message = runtime_config.lease_recovery_error_message
        self._internal_executors: dict[str, InternalTaskExecutor] = dict(internal_executors or {})
        self._internal_executors.setdefault(TASK_TYPE_SYSTEM, self.execute_system_task)

    async def poll_and_execute(self, limit: int = 10) -> dict[str, Any]:
        """Claim due tasks and execute each in its own transaction."""
        claimed_task_ids: list[int] = []
        recovered_task_ids: list[int] = []
        async with app_db_session() as session:
            repo = ScheduledTaskRepository(session)
            recovered_task_ids = await repo.recover_expired_running_tasks(limit=self.watchdog_recovery_limit)
            claimed = await repo.claim_due_tasks_with_lease(
                owner_instance_id=self.owner_instance_id,
                lease_ttl_seconds=self.lease_ttl_seconds,
                limit=limit,
            )
            # Service-level policy: keep recovery reason and reset stale errors on newly claimed tasks.
            if recovered_task_ids:
                await repo.set_error_message_for_task_ids(
                    task_ids=recovered_task_ids,
                    error_message=self.lease_recovery_error_message,
                )
            claimed_task_ids = [task.id for task in claimed]
            if claimed_task_ids:
                await repo.set_error_message_for_task_ids(
                    task_ids=claimed_task_ids,
                    error_message=None,
                )

        success_count = 0
        failed_count = 0
        skipped_count = 0

        for task_id in claimed_task_ids:
            try:
                executed = await self.execute_single_task(task_id)
                if executed:
                    success_count += 1
                else:
                    skipped_count += 1
            except Exception:
                failed_count += 1
                logger.exception("Scheduled task execution failed: task_id=%s", task_id)

        return {
            "recovered": len(recovered_task_ids),
            "claimed": len(claimed_task_ids),
            "success": success_count,
            "failed": failed_count,
            "skipped": skipped_count,
        }

    async def execute_single_task(self, task_id: int) -> bool:
        async with app_db_session() as session:
            repo = ScheduledTaskRepository(session)
            task = await repo.get_task_by_id(task_id)
            if not task or task.status != TASK_STATUS_RUNNING:
                return False

            owner_instance_id = task.owner_instance_id
            fencing_token = task.fencing_token
            if not owner_instance_id:
                logger.warning("Skipping task without owner_instance_id: task_id=%s", task_id)
                return False

            orchestration_run_id = uuid4().hex
            run: TaskRun = await repo.create_run(
                task=task,
                orchestration_run_id=orchestration_run_id,
            )
            logger.info(
                "[TASK][START] task_id=%s task_type=%s orchestration_run_id=%s",
                task.id,
                task.task_type,
                orchestration_run_id,
            )
            await self._commit_if_available(session)

            next_run_at = None
            if task.schedule_type == SCHEDULE_TYPE_CRON:
                next_run_at = compute_next_run_at(
                    schedule_type=task.schedule_type,
                    schedule_spec=task.schedule_spec,
                )

            lease_lost_event = asyncio.Event()
            heartbeat_task = asyncio.create_task(
                self._lease_heartbeat_loop(
                    task_id=task.id,
                    owner_instance_id=owner_instance_id,
                    fencing_token=fencing_token,
                    lease_lost_event=lease_lost_event,
                )
            )

            try:
                # Convert DB model to domain model for business logic
                domain_task = db_task_to_domain(task)

                # Dispatch to executor — all return TaskExecutionResult
                if task.execution_mode == EXECUTION_MODE_SANDBOX:
                    if task.task_type == TASK_TYPE_LIVEAPP_JOB:
                        liveapp_prep = await self.execute_liveapp_job_task(task)
                        exec_result = await self._dispatch_sandbox_task(
                            domain_task,
                            input_params=task.input_params,
                            extra_runtime_context=liveapp_prep.runtime_context,
                        )
                    else:
                        exec_result = await self._dispatch_sandbox_task(domain_task, input_params=task.input_params)
                else:
                    executor = self._internal_executors.get(domain_task.task_type)
                    if executor is None:
                        raise ValueError(
                            f"No internal executor registered for task_type={domain_task.task_type}"
                        )
                    exec_result = await executor(domain_task)

                if lease_lost_event.is_set():
                    finished_at = datetime.now(UTC)
                    duration_ms = int((finished_at - run.started_at).total_seconds() * 1000)
                    await repo.mark_run_failed(
                        run_id=run.id,
                        task_id=task.id,
                        error_message="Execution lease lost before completion",
                        result=None,
                        next_run_at=next_run_at,
                        task_status=TASK_STATUS_PENDING if next_run_at else TASK_STATUS_FAILED,
                        finished_at=finished_at,
                        duration_ms=duration_ms,
                    )
                    return False

                # --- Failure path ---
                if not exec_result.success:
                    error_message = (exec_result.error_message or "Task execution failed")[:500]
                    log_paths = self._persist_run_logs(
                        tenant_id=task.tenant_id,
                        task_id=task.id,
                        run_id=run.id,
                        attempt=run.attempt,
                        started_at=run.started_at,
                        stdout=exec_result.stdout,
                        stderr=exec_result.stderr,
                    )
                    if log_paths:
                        result = {
                            **(exec_result.payload or {}),
                            "stdout_log_path": log_paths.stdout_log_path,
                            "stderr_log_path": log_paths.stderr_log_path,
                            "has_logs": True,
                        }
                    else:
                        result = exec_result.payload

                    finished_at = datetime.now(UTC)
                    duration_ms = int((finished_at - run.started_at).total_seconds() * 1000)
                    await repo.mark_run_failed(
                        run_id=run.id,
                        task_id=task.id,
                        error_message=error_message,
                        result=result,
                        next_run_at=next_run_at,
                        task_status=TASK_STATUS_PENDING if next_run_at else TASK_STATUS_FAILED,
                        finished_at=finished_at,
                        duration_ms=duration_ms,
                    )
                    logger.warning(
                        "[TASK][END] task_id=%s orchestration_run_id=%s status=failed error=%s",
                        task.id,
                        orchestration_run_id,
                        error_message,
                    )
                    await self._dispatch_task_notification(
                        session=session,
                        task=task,
                        status="scheduled_task_failed",
                        title=f"Scheduled task failed: {task.name}",
                        payload={
                            "task_id": task.id,
                            "task_type": task.task_type,
                            "error": error_message,
                        },
                    )
                    return False

                # --- Success path ---
                log_paths = self._persist_run_logs(
                    tenant_id=task.tenant_id,
                    task_id=task.id,
                    run_id=run.id,
                    attempt=run.attempt,
                    started_at=run.started_at,
                    stdout=exec_result.stdout,
                    stderr=exec_result.stderr,
                )
                result = exec_result.payload
                if log_paths:
                    result = {
                        **result,
                        "stdout_log_path": log_paths.stdout_log_path,
                        "stderr_log_path": log_paths.stderr_log_path,
                        "has_logs": True,
                    }

                finished_at = datetime.now(UTC)
                duration_ms = int((finished_at - run.started_at).total_seconds() * 1000)
                await repo.mark_run_success(
                    run_id=run.id,
                    task_id=task.id,
                    result=result,
                    next_run_at=next_run_at,
                    task_status=TASK_STATUS_PENDING if next_run_at else TASK_STATUS_COMPLETED,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                )
                logger.info(
                    "[TASK][END] task_id=%s orchestration_run_id=%s status=success duration_ms=%s",
                    task.id,
                    orchestration_run_id,
                    getattr(run, "duration_ms", None),
                )
                await self._dispatch_task_notification(
                    session=session,
                    task=task,
                    status="scheduled_task_completed",
                    title=f"Scheduled task completed: {task.name}",
                    payload={
                        "task_id": task.id,
                        "task_type": task.task_type,
                        "result": result,
                    },
                )
                return True
            except Exception as e:
                await self._rollback_if_available(session)

                # Persist logs — only raw stdout/stderr; no-op if empty
                log_paths = self._persist_run_logs(
                    tenant_id=task.tenant_id,
                    task_id=task.id,
                    run_id=run.id,
                    attempt=run.attempt,
                    started_at=run.started_at,
                    stdout="",
                    stderr="",
                )

                if log_paths:
                    result = {
                        "stdout_log_path": log_paths.stdout_log_path,
                        "stderr_log_path": log_paths.stderr_log_path,
                        "has_logs": True,
                    }
                else:
                    result = None

                error_message = str(e)[:500]
                finished_at = datetime.now(UTC)
                duration_ms = int((finished_at - run.started_at).total_seconds() * 1000)
                await repo.mark_run_failed(
                    run_id=run.id,
                    task_id=task.id,
                    error_message=error_message,
                    result=result,
                    next_run_at=next_run_at,
                    task_status=TASK_STATUS_PENDING if next_run_at else TASK_STATUS_FAILED,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                )

                logger.exception(
                    "[TASK][END] task_id=%s orchestration_run_id=%s status=failed",
                    task.id,
                    orchestration_run_id,
                )
                await self._dispatch_task_notification(
                    session=session,
                    task=task,
                    status="scheduled_task_failed",
                    title=f"Scheduled task failed: {task.name}",
                    payload={
                        "task_id": task.id,
                        "task_type": task.task_type,
                        "error": str(e),
                    },
                )
                await self._commit_if_available(session)
                raise
            finally:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def _dispatch_sandbox_task(
        self,
        task: ScheduledTaskDomain,
        input_params: dict | None = None,
        timeout_seconds: int = 300,
        extra_runtime_context: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        """Submit a task to sandbox_service and return the result dict.

        Returns the result dict regardless of exit code.  The caller decides
        whether a non-zero exit code constitutes a task failure.

        Raises SandboxError only for transport-level failures (HTTP / timeout).

        Args:
            task: The scheduled task to execute
            input_params: Additional parameters to pass to the sandbox task
            timeout_seconds: Execution timeout
            extra_runtime_context: Additional context to merge into TASK_RUNTIME_CONTEXT
        """
        # Get sandbox execution params from domain model
        sandbox_params = task.get_sandbox_execution_params()
        if not sandbox_params:
            raise SandboxExecutionError(f"Task type {task.task_type} does not support sandbox execution")

        # Build runtime context
        runtime_context: dict[str, Any] = {"tenant_id": task.tenant_id, "task_id": task.id}
        if extra_runtime_context:
            runtime_context.update(extra_runtime_context)
        input_params = input_params or {}

        # Build command with environment variables
        # Use export to ensure env vars are available for all subsequent commands in the chain
        params_json = shlex.quote(json.dumps(input_params))
        ctx_json = shlex.quote(json.dumps(runtime_context))
        command = (
            f"export TASK_INPUT_PARAMS={params_json} TASK_RUNTIME_CONTEXT={ctx_json}; {sandbox_params.command_template}"
        )

        logger.info(
            "[SANDBOX][START] task_id=%s task_type=%s target_id=%s entrypoint=%s",
            task.id,
            task.task_type,
            sandbox_params.target_id,
            sandbox_params.entrypoint,
        )

        # Build execution context for client (identity/tracing only)
        execution_context = SandboxExecutionContext(
            tenant_id=task.tenant_id,
            user_id=task.user_id,
            task_id=task.id,
        )

        # Determine working_dir and app_root_subpath for app workspace binding
        # For liveapp jobs, extra_runtime_context contains app_id and environment
        working_dir = "/workspace"
        app_root_subpath: str | None = None

        if extra_runtime_context and "app_id" in extra_runtime_context:
            app_id = extra_runtime_context.get("app_id")
            environment = extra_runtime_context.get("environment", "prod")
            app_root_subpath = f"tenants/tenant_{task.tenant_id}/apps/app_{app_id}/env/{environment}"
            working_dir = "/app_root"
            logger.info(
                "[SANDBOX] Mounting app workspace: app_id=%s environment=%s app_root_subpath=%s",
                app_id,
                environment,
                app_root_subpath,
            )

        # Execute via shared client
        client = SandboxClient()
        try:
            result = await client.execute(
                command=command,
                timeout_seconds=timeout_seconds,
                context=execution_context,
                working_dir=working_dir,
                app_root_subpath=app_root_subpath,
            )
        finally:
            await client.close()

        logger.info(
            "[SANDBOX][END] task_id=%s exit_code=%s",
            task.id,
            result.exit_code,
        )

        # Build payload — what goes into DB run.result
        payload: dict[str, Any] = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
        }
        try:
            parsed = json.loads(result.stdout)
            if isinstance(parsed, dict):
                payload["output"] = parsed
        except (json.JSONDecodeError, ValueError):
            pass

        # Normalize into unified result — executor decides success/failure
        success = result.exit_code == 0
        error_message: str | None = None
        if not success:
            error_message = result.stderr or f"Sandbox exited with code {result.exit_code}"

        return TaskExecutionResult(
            success=success,
            payload=payload,
            stdout=result.stdout,
            stderr=result.stderr,
            error_message=error_message,
        )

    async def _commit_if_available(self, session) -> None:
        """Commit current transaction when running with a real AsyncSession.

        Test doubles may not expose commit(); this method keeps execution logic
        compatible with those fakes while still allowing early durability in
        production.
        """
        commit = getattr(session, "commit", None)
        if commit is None:
            return
        maybe_awaitable = commit()
        if asyncio.iscoroutine(maybe_awaitable):
            await maybe_awaitable

    async def _rollback_if_available(self, session) -> None:
        """Rollback current transaction when running with a real AsyncSession."""
        rollback = getattr(session, "rollback", None)
        if rollback is None:
            return
        maybe_awaitable = rollback()
        if asyncio.iscoroutine(maybe_awaitable):
            await maybe_awaitable

    def _persist_run_logs(
        self,
        *,
        tenant_id: int,
        task_id: int,
        run_id: int,
        attempt: int,
        started_at: datetime,
        stdout: str,
        stderr: str,
    ) -> RunLogPaths | None:
        """Persist run stdout/stderr to tenant-scoped files.

        Only handles raw execution output.  The error_message for failures
        is persisted separately via the service layer.

        Returns RunLogPaths on success, None if writing fails or nothing to write.
        """
        if not stdout and not stderr:
            return None

        try:
            writer = RunLogWriter(EnvConfig.DATA_ROOT_PATH)
            return writer.write_logs(
                tenant_id=tenant_id,
                task_id=task_id,
                run_id=run_id,
                attempt=attempt,
                started_at=started_at,
                stdout_content=stdout,
                stderr_content=stderr,
            )
        except Exception:
            logger.exception(
                "Failed to persist run logs: task_id=%s run_id=%s",
                task_id,
                run_id,
            )
            return None

    def _build_task_execution_context(self, *, task: ScheduledTask) -> TaskExecutionContext:
        """Build default task execution context for internal task handlers."""
        task_id = getattr(task, "id", None)
        tenant_id = getattr(task, "tenant_id", None)
        if not isinstance(task_id, int) or not isinstance(tenant_id, int):
            raise ValueError("Scheduled task context requires integer task.id and task.tenant_id")

        return {
            "task_id": task_id,
            "tenant_id": tenant_id,
            "user_id": getattr(task, "user_id", None),
            "input_params": dict(getattr(task, "input_params", None) or {}),
        }

    async def _lease_heartbeat_loop(
        self,
        *,
        task_id: int,
        owner_instance_id: str,
        fencing_token: int,
        lease_lost_event: asyncio.Event,
    ) -> None:
        """Keep renewing task lease; signal when ownership is lost."""
        while not lease_lost_event.is_set():
            await asyncio.sleep(max(self.heartbeat_interval_seconds, 1))
            async with app_db_session() as heartbeat_session:
                repo = ScheduledTaskRepository(heartbeat_session)
                renewed = await repo.heartbeat_lease(
                    task_id=task_id,
                    owner_instance_id=owner_instance_id,
                    fencing_token=fencing_token,
                    lease_ttl_seconds=self.lease_ttl_seconds,
                )
                if not renewed:
                    logger.warning(
                        "Scheduled task lease lost: task_id=%s owner=%s token=%s",
                        task_id,
                        owner_instance_id,
                        fencing_token,
                    )
                    lease_lost_event.set()
                    return

    async def _dispatch_task_notification(
        self,
        *,
        session,
        task: ScheduledTask,
        status: str,
        title: str,
        payload: dict[str, Any],
    ) -> None:
        notification_service = NotificationService(session)
        event = NotificationEvent(
            tenant_id=task.tenant_id,
            user_id=task.user_id,
            event_type=status,
            title=title,
            payload=payload,
        )
        await notification_service.dispatch_event(
            event,
            channel_override=task.notification_channels,
        )

    # ------------------------------------------------------------------
    # Task Execution Methods (type-specific execution logic)
    # ------------------------------------------------------------------

    async def execute_liveapp_job_task(self, task: ScheduledTask) -> LiveAppJobExecutionResult:
        """Execute a liveapp job task.

        Validates app exists, builds runtime context with DB connection,
        and returns context for sandbox execution.

        Args:
            task: The scheduled task to execute

        Returns:
            LiveAppJobExecutionResult with app metadata and runtime_context for sandbox

        Raises:
            ValueError: If task config is invalid or app/data source not found
        """
        from apps.shared.data_source.repository import DataSourceRepository
        from apps.shared.live_app.repository import LiveAppRepository
        from apps.shared.live_app.workspace import _bootstrap_python_sdk, get_app_path

        task_config: LiveAppJobTaskConfig = task.task_config
        app_id = task_config["app_id"]
        job_name = task_config["job_name"]
        entrypoint = task_config["entrypoint"]
        environment = task_config.get("environment", "prod")

        # Ensure SDK is bootstrapped for this environment before job execution.
        # This is a defensive check: SDK should have been copied during app creation,
        # but older apps or environments accessed only via CLI may be missing it.
        try:
            app_path = Path(get_app_path(task.tenant_id, app_id, environment=environment, create=False))
            _bootstrap_python_sdk(app_path)
        except Exception:
            logger.exception(
                "Failed to bootstrap Python SDK for app_id=%s environment=%s (non-fatal, job may fail)",
                app_id,
                environment,
            )

        # Validate app exists and get its data_source_id
        async with app_db_session() as db_session:
            # First verify app exists
            app_repo = LiveAppRepository(db_session)
            live_app = await app_repo.get_for_tenant(app_id=app_id, tenant_id=task.tenant_id)

            if not live_app:
                raise ValueError(f"Live app {app_id} not found for tenant {task.tenant_id}")

            if not live_app.data_source_id:
                raise ValueError(f"Live app {app_id} has no configured data source for tenant {task.tenant_id}")

            # Get the data source by ID
            ds_repo = DataSourceRepository(db_session)
            data_source = await ds_repo.get_by_id_and_tenant(
                data_source_id=live_app.data_source_id,
                tenant_id=task.tenant_id,
            )

            if not data_source or not data_source.managed:
                raise ValueError(
                    f"Data source {live_app.data_source_id} is not managed or not found for tenant {task.tenant_id}. "
                    "Live app jobs require a managed PostgreSQL data source."
                )

            # Convert DB model to domain model to use DatabaseConnectionVO.to_url()
            data_source_domain = db_data_source_to_domain(data_source)
            db_connection_string = data_source_domain.connection.to_url(db_type=data_source.type)

        # Derive schema name from environment using consistent logic
        schema_name = self._schema_for_environment(app_id=app_id, environment=environment)

        # Generate short-lived access token for SDK authentication
        settings = get_settings()
        expires = datetime.now(UTC) + timedelta(hours=1)
        access_token = jwt.encode(
            {
                "sub": f"task_{task.id}",
                "user_id": task.user_id,
                "tenant_id": task.tenant_id,
                "role": "system",  # System role for job execution
                "exp": expires,
            },
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )

        # Determine API base URL for SDK calls
        # Jobs run in sandbox and need to call back to the tenant app service
        from apps.config import EnvConfig

        api_base_url = EnvConfig.SANDBOX_RUNNER_API_BASE_URL

        runtime_context = {
            "tenant_id": task.tenant_id,
            "app_id": app_id,
            "job_name": job_name,
            "environment": environment,
            "schema_name": schema_name,
            "data_source_id": data_source.id,
            "db_connection_string": db_connection_string,  # For direct psycopg2 usage
            # NEW: For SDK-based access
            "access_token": access_token,
            "api_base_url": api_base_url,
        }

        return LiveAppJobExecutionResult(
            app_id=app_id,
            job_name=job_name,
            entrypoint=entrypoint,
            runtime_context=runtime_context,
        )

    async def execute_system_task(self, task: ScheduledTaskDomain) -> TaskExecutionResult:
        """Execute a system task.

        Resolves handler_ref from task_config, validates against allowlist,
        imports and executes the module:function.

        Args:
            task: The scheduled task to execute

        Returns:
            Dictionary with execution result

        Raises:
            ValueError: If handler_ref is missing, invalid, or not in allowlist
        """
        import importlib
        import inspect
        from collections.abc import Callable
        from typing import Any as TypingAny

        # Restrict dynamic import to known builtin system handlers only.
        ALLOWED_SYSTEM_HANDLER_REFS: set[str] = {
            "apps.shared.tasks.system.jobs.vector_sync:sync_to_vector_db",
            "apps.shared.tasks.system.jobs.vector_sync:cleanup_orphaned_vectors",
            "apps.shared.tasks.system.jobs.asset_sync:sync_asset_metadata_for_all",
            "apps.shared.tasks.system.jobs.cleanup:cleanup_old_charts",
            "apps.shared.tasks.system.jobs.cleanup:cleanup_expired_temp_tables",
            "apps.shared.tasks.system.jobs.document_parse:run_document_parse_jobs",
            "apps.shared.tasks.system.jobs.document_sync:run_document_sync_jobs",
        }

        def _resolve_handler(handler_ref: str) -> Callable[..., TypingAny]:
            try:
                module_path, func_name = handler_ref.split(":", 1)
            except ValueError as exc:
                raise ValueError(f"Invalid system handler_ref format: {handler_ref!r}") from exc

            module = importlib.import_module(module_path)
            handler = getattr(module, func_name, None)
            if handler is None or not callable(handler):
                raise ValueError(f"System handler target not found/callable: {handler_ref!r}")
            return handler

        def _build_handler_kwargs(
            handler: Callable[..., TypingAny], context: dict[str, TypingAny], task_input_params: dict[str, TypingAny]
        ) -> dict[str, TypingAny]:
            input_params = dict(task_input_params or {})
            kwargs: dict[str, TypingAny] = dict(input_params)

            signature = inspect.signature(handler)
            accepts_var_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()
            )
            if "task_context" in signature.parameters:
                kwargs["task_context"] = context

            if accepts_var_kwargs:
                kwargs.setdefault("task_context", context)
                return kwargs

            # Keep only supported named kwargs for strict handlers.
            return {k: v for k, v in kwargs.items() if k in signature.parameters}

        async def _invoke_handler(
            handler: Callable[..., TypingAny], kwargs: dict[str, TypingAny]
        ) -> SystemTaskHandlerResult:
            result = handler(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            if not isinstance(result, SystemTaskHandlerResult):
                raise ValueError("System handler must return SystemTaskHandlerResult")
            return result

        # Extract handler_ref from task_config
        handler_ref = (task.task_config or {}).get("handler_ref", "")
        if not handler_ref:
            raise ValueError(f"System task missing handler_ref in task_config: task_id={task.id}")
        if handler_ref not in ALLOWED_SYSTEM_HANDLER_REFS:
            raise ValueError(f"Unknown system handler_ref: {handler_ref!r}")

        # Build execution context
        context = {
            "tenant_id": task.tenant_id,
            "task_id": task.id,
            "user_id": task.user_id,
            "input_params": task.input_params or {},
        }

        # Resolve and execute handler
        handler = _resolve_handler(handler_ref)
        kwargs = _build_handler_kwargs(handler=handler, context=context, task_input_params=task.input_params)
        logger.debug("Executing system task handler_ref=%s kwargs_keys=%s", handler_ref, list(kwargs.keys()))
        handler_result = await _invoke_handler(handler, kwargs)
        return TaskExecutionResult(
            success=handler_result.outcome != "failed",
            payload=handler_result.to_payload(),
            error_message=handler_result.error_message,
        )

    @staticmethod
    def _schema_for_environment(app_id: int, environment: str) -> str:
        """Derive schema name from app_id and environment.

        Matches LiveAppService._schema_for_environment() logic:
        - prod: app_{app_id}
        - dev/test: app_{app_id}_{environment}

        Args:
            app_id: Live app identifier
            environment: Environment name (dev, test, or prod)

        Returns:
            Schema name string (e.g., "app_123" or "app_123_dev")
        """
        if environment == "prod":
            return f"app_{app_id}"
        return f"app_{app_id}_{environment}"
