"""Agent tool for creating unified scheduled tasks."""

from datetime import UTC, datetime

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator, model_validator

from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.notification.domain import NotificationChannelType, is_valid_notification_channel
from apps.shared.tasks.adapters import scheduled_task_to_response_payload
from apps.shared.tasks.domain import (
    EXECUTION_MODE_INTERNAL,
    EXECUTION_MODE_SANDBOX,
    SCHEDULE_TYPE_CRON,
    SCHEDULE_TYPE_ONCE,
    TASK_TYPE_AGENT_RUN,
    TASK_TYPE_LIVEAPP_JOB,
    TASK_TYPE_SKILL_CALL,
    LiveAppJobTaskConfig,
    ScheduledTaskScheduleType,
    SkillCallTaskConfig,
    TaskConfig,
    normalize_agent_run_task_config,
)
from apps.shared.tasks.scheduling import compute_next_run_at, normalize_schedule_spec
from apps.shared.tasks.service import ScheduledTaskService
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_rbac import tool_rbac_denied
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)


class ScheduleTaskSchema(BaseModel):
    """Schema for scheduling tasks with dynamic task configuration.

    This schema uses a task_type + task_config pattern where task_config
    is a flexible dict that adapts based on the task_type:

    - 'agent_run': {"agent_id": int (optional), "task_description": str (optional), "origin_thread_id": str (optional)}
    - 'skill_call': {"skill_id": str, "entrypoint": str (optional)}
    - 'liveapp_job': {"app_id": int, "job_name": str, "entrypoint": str, "environment": str (default: 'prod')}

    Note: 'system' task type is NOT available via agent tools - system tasks are
    managed internally by SystemTaskReconciler only.

    See apps/shared/tasks/domain.py for full TaskConfig type definitions.
    """

    task_description: str = Field(..., description="Human-readable task description")
    schedule_type: ScheduledTaskScheduleType = SCHEDULE_TYPE_ONCE
    schedule_spec: str = ""
    schedule_timezone: str | None = None
    notification_channels: list[NotificationChannelType] | None = None
    task_type: str = Field(
        default=TASK_TYPE_AGENT_RUN,
        description="Task execution type: 'agent_run' (default), 'skill_call', or 'liveapp_job'",
    )
    task_config: TaskConfig = Field(
        default_factory=dict,
        description="Dynamic configuration dict based on task_type. Required fields vary by task_type.",
    )

    @field_validator("task_description")
    @classmethod
    def _validate_task_description(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task_description is required")
        return value

    @field_validator("notification_channels")
    @classmethod
    def _validate_notification_channels(cls, value: list[NotificationChannelType] | None):
        if value is None:
            return value
        invalid_channels = [channel for channel in value if not is_valid_notification_channel(channel)]
        if invalid_channels:
            raise ValueError(f"Invalid notification channels: {invalid_channels}")
        return value

    @model_validator(mode="after")
    def _validate_schedule_spec(self):
        if self.schedule_type in {SCHEDULE_TYPE_ONCE, SCHEDULE_TYPE_CRON} and not self.schedule_spec:
            raise ValueError(f"schedule_spec is required for {self.schedule_type} schedule")

        # Validate task_type is supported (system tasks excluded - internal only)
        valid_types = {TASK_TYPE_AGENT_RUN, TASK_TYPE_SKILL_CALL, TASK_TYPE_LIVEAPP_JOB}
        if self.task_type not in valid_types:
            raise ValueError(
                f"task_type must be one of: {', '.join(sorted(valid_types))}. Note: 'system' tasks are managed internally."
            )

        # Validate task_config has required fields based on task_type
        if self.task_type == TASK_TYPE_SKILL_CALL:
            if not self.task_config.get("skill_id"):
                raise ValueError("task_config must include 'skill_id' for skill_call tasks")
        elif self.task_type == TASK_TYPE_LIVEAPP_JOB:
            required_keys = ["app_id", "job_name", "entrypoint"]
            missing = [k for k in required_keys if k not in self.task_config]
            if missing:
                raise ValueError(f"task_config missing required keys for liveapp_job: {missing}")
        elif self.task_type == TASK_TYPE_AGENT_RUN:
            # Agent run tasks can auto-fill from runtime context if not provided
            pass

        return self


class UpdateScheduledTaskSchema(BaseModel):
    task_id: int = Field(..., gt=0)
    task_description: str | None = None
    task_type: str | None = None
    task_config: TaskConfig | None = None
    schedule_type: ScheduledTaskScheduleType | None = None
    schedule_spec: str | None = None
    schedule_timezone: str | None = None
    notification_channels: list[NotificationChannelType] | None = None

    @field_validator("task_description")
    @classmethod
    def _validate_optional_task_description(cls, value: str | None):
        if value is None:
            return value
        if not value.strip():
            raise ValueError("task_description cannot be empty")
        return value

    @field_validator("task_type")
    @classmethod
    def _validate_task_type(cls, value: str | None):
        if value is None:
            return value
        valid_types = {TASK_TYPE_AGENT_RUN, TASK_TYPE_SKILL_CALL, TASK_TYPE_LIVEAPP_JOB}
        if value not in valid_types:
            raise ValueError(
                f"task_type must be one of: {', '.join(sorted(valid_types))}. Note: 'system' tasks are managed internally."
            )
        return value

    @field_validator("schedule_spec")
    @classmethod
    def _validate_optional_schedule_spec(cls, value: str | None):
        if value is None:
            return value
        if not value.strip():
            raise ValueError("schedule_spec cannot be empty")
        return value

    @field_validator("notification_channels")
    @classmethod
    def _validate_optional_notification_channels(cls, value: list[NotificationChannelType] | None):
        if value is None:
            return value
        invalid_channels = [channel for channel in value if not is_valid_notification_channel(channel)]
        if invalid_channels:
            raise ValueError(f"Invalid notification channels: {invalid_channels}")
        return value

    @model_validator(mode="after")
    def _validate_cross_fields(self):
        if self.schedule_type is not None and self.schedule_spec is None:
            raise ValueError("schedule_spec is required when changing schedule_type")
        # Validate task_config based on task_type if provided
        if self.task_type is not None and self.task_config is not None:
            if self.task_type == TASK_TYPE_SKILL_CALL:
                if not self.task_config.get("skill_id"):
                    raise ValueError("task_config must include 'skill_id' for skill_call tasks")
            elif self.task_type == TASK_TYPE_LIVEAPP_JOB:
                required_keys = ["app_id", "job_name", "entrypoint"]
                missing = [k for k in required_keys if k not in self.task_config]
                if missing:
                    raise ValueError(f"task_config missing required keys for liveapp_job: {missing}")
        if (
            self.task_description is None
            and self.task_type is None
            and self.task_config is None
            and self.schedule_type is None
            and self.schedule_spec is None
            and self.schedule_timezone is None
            and self.notification_channels is None
        ):
            raise ValueError("No update fields provided")
        return self


def _actor_ctx(runtime) -> ActorContext:
    return ActorContext(
        tenant_id=runtime.user.tenant_id,
        user_id=runtime.user.user_id,
        user_role=runtime.user.role,
    )


def _task_payload(task) -> dict:
    return scheduled_task_to_response_payload(task).model_dump(mode="json")


@tool(args_schema=ScheduleTaskSchema)
async def schedule_task(
    task_description: str,
    config: RunnableConfig,
    schedule_type: ScheduledTaskScheduleType = SCHEDULE_TYPE_ONCE,
    schedule_spec: str = "",
    schedule_timezone: str | None = None,
    notification_channels: list[NotificationChannelType] | None = None,
    # Unified task routing: task_type determines execution strategy
    task_type: str = TASK_TYPE_AGENT_RUN,
    # Dynamic configuration based on task_type (see ScheduleTaskSchema docstring for examples)
    task_config: dict | None = None,
) -> ToolResult:
    """Schedule a future task for the current user.

    Use this tool when the user asks to run a task later or on a recurring cron schedule.

    **Scheduling:**
    - For `once` schedule: Use relative offset like `+5m`, `+2h`, `+1d`; or ISO datetime with timezone
    - For `cron` schedule: Use 5-field cron expression like `0 9 * * 1`

    **Task Types & Configuration:**

    1. **agent_run** (default): Execute an agent conversation
       ```python
       task_config = {
           "agent_id": "optional-agent-id",  # Auto-filled from runtime if omitted
           "task_description": "What to do",  # Optional, uses outer task_description if omitted
           "origin_thread_id": "thread-123"   # Auto-filled from runtime if omitted
       }
       ```

    2. **skill_call**: Execute a registered skill in sandbox
       ```python
       task_config = {
           "skill_id": "weather-skill",        # Required: registered skill ID
           "entrypoint": "skills.weather:run"  # Optional: module entrypoint override
       }
       ```

    3. **liveapp_job**: Execute a live app Python job script in sandbox
       ```python
       task_config = {
           "app_id": 123,                      # Required: live app ID
           "job_name": "etl_pipeline",         # Required: job script name
           "entrypoint": "jobs/etl_pipeline.py", # Required: script path
           "environment": "prod"               # Optional: dev/test/prod (default: prod)
       }
       ```

    4. **system**: Execute internal system tasks (admin only)
       ```python
       task_config = {
           "system_task_key": "cleanup_old_data",  # Required: registered system task
           "params": {"retention_days": 30}        # Optional: task-specific parameters
       }
       ```

    **Examples:**
    ```python
    # Schedule agent run tomorrow
    await schedule_task.invoke({
        "task_description": "Generate daily report",
        "schedule_type": "once",
        "schedule_spec": "+1d",
        "task_type": "agent_run",
        "task_config": {}
    })

    # Schedule skill call every morning at 9 AM
    await schedule_task.invoke({
        "task_description": "Fetch weather data",
        "schedule_type": "cron",
        "schedule_spec": "0 9 * * *",
        "task_type": "skill_call",
        "task_config": {"skill_id": "weather-skill"}
    })

    # Schedule live app job weekly
    await schedule_task.invoke({
        "task_description": "Sync external data",
        "schedule_type": "cron",
        "schedule_spec": "0 6 * * 1",
        "task_type": "liveapp_job",
        "task_config": {
            "app_id": 456,
            "job_name": "sync_weather",
            "entrypoint": "jobs/sync_weather.py",
            "environment": "prod"
        }
    })
    ```
    """
    try:
        runtime = extract_runtime_context(config)
        effective_timezone = schedule_timezone or runtime.user.timezone_iana or "UTC"
        normalized_spec = normalize_schedule_spec(
            schedule_type,
            schedule_spec,
            timezone_name=effective_timezone if schedule_type == SCHEDULE_TYPE_CRON else None,
        )
        now_utc = datetime.now(UTC)
        next_run_at = compute_next_run_at(
            schedule_type=schedule_type,
            schedule_spec=normalized_spec,
            runtime_timezone=runtime.user.timezone_iana,
            now=now_utc,
        )
        if next_run_at is None:
            return ToolResult.error_result(
                f"next run time must be in the future (current UTC: {now_utc.isoformat()})",
                code="INVALID_NEXT_RUN_AT",
            )

        channels = notification_channels
        config_dict = task_config or {}

        # Determine execution parameters based on task_type
        if task_type == TASK_TYPE_SKILL_CALL:
            resolved_task_type = TASK_TYPE_SKILL_CALL
            resolved_execution_mode = EXECUTION_MODE_SANDBOX
            resolved_task_config: SkillCallTaskConfig = {
                "skill_id": config_dict.get("skill_id", ""),
                "entrypoint": config_dict.get("entrypoint", ""),
            }
            input_params = config_dict.get("input_params")
        elif task_type == TASK_TYPE_LIVEAPP_JOB:
            # Validate required liveapp job parameters from task_config
            required_keys = ["app_id", "job_name", "entrypoint"]
            missing = [k for k in required_keys if k not in config_dict]
            if missing:
                return ToolResult.error_result(
                    f"task_config missing required keys for liveapp_job: {missing}",
                    code="LIVEAPP_JOB_MISSING_PARAMS",
                )
            resolved_task_type = TASK_TYPE_LIVEAPP_JOB
            resolved_execution_mode = EXECUTION_MODE_SANDBOX
            resolved_task_config: LiveAppJobTaskConfig = {
                "app_id": config_dict["app_id"],
                "job_name": config_dict["job_name"],
                "entrypoint": config_dict["entrypoint"],
                "environment": config_dict.get("environment", "prod"),
            }
            input_params = config_dict.get("input_params")
        else:
            # Default to agent_run (internal execution)
            resolved_task_type = TASK_TYPE_AGENT_RUN
            resolved_execution_mode = EXECUTION_MODE_INTERNAL
            resolved_task_config = normalize_agent_run_task_config(
                {
                    "agent_id": config_dict.get("agent_id", runtime.agent_id),
                    "task_description": config_dict.get("task_description", task_description.strip()),
                    "origin_thread_id": config_dict.get("origin_thread_id", runtime.thread_id),
                }
            )
            input_params = None

        async with app_db_session() as db_session:
            denied = await tool_rbac_denied(
                db_session,
                runtime.user.tenant_id,
                runtime.user.role,
                TenantAppPermissions.SCHEDULED_TASKS_WRITE,
                denied_message="You do not have permission to create scheduled tasks",
            )
            if denied:
                return denied

            service = ScheduledTaskService.create(
                tenant_id=runtime.user.tenant_id,
                db_session=db_session,
            )
            created = await service.create_task_with_artifact(
                user_id=runtime.user.user_id,
                name=task_description,
                task_type=resolved_task_type,
                task_config=resolved_task_config,
                schedule_type=schedule_type,
                schedule_spec=normalized_spec,
                next_run_at=next_run_at,
                notification_channels=channels,
                thread_id=runtime.thread_id,
                execution_mode=resolved_execution_mode,
                input_params=input_params,
            )
            task = created.task
            artifact_payload = created.artifact.model_dump()

        logger.info(
            "Scheduled agent task created: task_id=%s tenant=%s user=%s agent=%s",
            task.id,
            runtime.user.tenant_id,
            runtime.user.user_id,
            runtime.agent_id,
        )
        return ToolResult.success(
            {
                "task_id": task.id,
                "task_type": task.task_type,
                "schedule_type": task.schedule_type,
                "schedule_timezone": (
                    task.schedule_spec.get("timezone")
                    if isinstance(task.schedule_spec, dict) and isinstance(task.schedule_spec.get("timezone"), str)
                    else "UTC"
                ),
                "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                "status": task.status,
                "artifact": artifact_payload,
            }
        )
    except ValueError as e:
        return ToolResult.error_result(str(e), code="SCHEDULE_VALIDATION_ERROR")
    except Exception as e:
        logger.exception("Failed to schedule task")
        return ToolResult.error_result(
            f"Failed to schedule task: {e}",
            code="SCHEDULE_TASK_FAILED",
        )


@tool(args_schema=UpdateScheduledTaskSchema)
async def update_scheduled_task(
    task_id: int,
    config: RunnableConfig,
    task_description: str | None = None,
    task_type: str | None = None,
    task_config: dict | None = None,
    schedule_type: ScheduledTaskScheduleType | None = None,
    schedule_spec: str | None = None,
    schedule_timezone: str | None = None,
    notification_channels: list[NotificationChannelType] | None = None,
) -> ToolResult:
    """Update an existing scheduled task for the current user.

    To stop a task permanently, use `cancel_scheduled_task` instead — cancelled tasks
    cannot be updated via this tool.

    `schedule_spec` rules:
    - For `once`, use relative offset like `+5m`, `+2h`, `+1d`; or
      ISO datetime with timezone like `2026-03-30T12:00:00+00:00`.
    - For `cron`, use standard 5-field cron expression, for example `0 9 * * 1`.

    **Task Types & Configuration:** (when updating task_config)

    1. **agent_run** (default):
       ```python
       task_config = {
           "agent_id": "optional-agent-id",
           "task_description": "What to do",
           "origin_thread_id": "thread-123",
       }
       ```

    2. **skill_call**:
       ```python
       task_config = {
           "skill_id": "weather-skill",
           "entrypoint": "skills.weather:run"
       }
       ```


    3. **liveapp_job**:
       ```python
       task_config = {
           "app_id": 123,
           "job_name": "etl_pipeline",
           "entrypoint": "jobs/etl_pipeline.py",
           "environment": "prod"
       }
       ```
    """
    try:
        runtime = extract_runtime_context(config)

        async with app_db_session() as db_session:
            service = ScheduledTaskService.create(
                tenant_id=runtime.user.tenant_id,
                db_session=db_session,
            )
            task = await service.get_task_for_actor(task_id=task_id, actor=_actor_ctx(runtime))

            effective_schedule_type = schedule_type or task.schedule_type
            has_schedule_change = schedule_type is not None or schedule_spec is not None

            if schedule_spec is not None:
                effective_timezone = schedule_timezone or runtime.user.timezone_iana or "UTC"
                normalized_spec = normalize_schedule_spec(
                    effective_schedule_type,
                    schedule_spec,
                    timezone_name=effective_timezone if effective_schedule_type == SCHEDULE_TYPE_CRON else None,
                )
            else:
                normalized_spec = task.schedule_spec
                if (
                    effective_schedule_type == SCHEDULE_TYPE_CRON
                    and schedule_timezone is not None
                    and isinstance(normalized_spec, dict)
                    and isinstance(normalized_spec.get("cron"), str)
                ):
                    normalized_spec = normalize_schedule_spec(
                        effective_schedule_type,
                        normalized_spec["cron"],
                        timezone_name=schedule_timezone,
                    )

            if has_schedule_change:
                now_utc = datetime.now(UTC)
                next_run_at = compute_next_run_at(
                    schedule_type=effective_schedule_type,
                    schedule_spec=normalized_spec,
                    runtime_timezone=runtime.user.timezone_iana,
                    now=now_utc,
                )
                if next_run_at is None:
                    return ToolResult.error_result(
                        f"next run time must be in the future (current UTC: {now_utc.isoformat()})",
                        code="INVALID_NEXT_RUN_AT",
                    )
            else:
                next_run_at = task.next_run_at

            task = await service.update_task_for_actor(
                task_id=task_id,
                actor=_actor_ctx(runtime),
                task_description=task_description,
                task_type=task_type,
                task_config=task_config,
                schedule_type=effective_schedule_type if schedule_type is not None else None,
                schedule_spec=normalized_spec if schedule_type is not None or schedule_spec is not None else None,
                next_run_at=next_run_at,
                notification_channels=notification_channels,
            )

        logger.info(
            "Scheduled task updated: task_id=%s tenant=%s user=%s",
            task_id,
            runtime.user.tenant_id,
            runtime.user.user_id,
        )
        return ToolResult.success(
            {
                "task_id": task.id,
                "task_type": task.task_type,
                "schedule_type": task.schedule_type,
                "schedule_timezone": (
                    task.schedule_spec.get("timezone")
                    if isinstance(task.schedule_spec, dict) and isinstance(task.schedule_spec.get("timezone"), str)
                    else "UTC"
                ),
                "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
                "status": task.status,
            }
        )
    except ValueError as e:
        return ToolResult.error_result(str(e), code="SCHEDULE_VALIDATION_ERROR")
    except Exception as e:
        logger.exception("Failed to update scheduled task")
        return ToolResult.error_result(
            f"Failed to update scheduled task: {e}",
            code="UPDATE_SCHEDULE_TASK_FAILED",
        )


@tool
async def cancel_scheduled_task(task_id: int, config: RunnableConfig) -> ToolResult:
    """Cancel an existing scheduled task for the current user.

    Use `list_scheduled_tasks` first when the user did not provide `task_id`.
    """
    try:
        if task_id <= 0:
            return ToolResult.error_result(
                "task_id must be a positive integer",
                code="INVALID_TASK_ID",
            )

        runtime = extract_runtime_context(config)
        async with app_db_session() as db_session:
            service = ScheduledTaskService.create(
                tenant_id=runtime.user.tenant_id,
                db_session=db_session,
            )
            cancelled = await service.cancel_task_for_actor(
                task_id=task_id,
                actor=_actor_ctx(runtime),
            )
            if not cancelled:
                return ToolResult.error_result(
                    f"Failed to cancel scheduled task: {task_id}",
                    code="CANCEL_SCHEDULE_TASK_FAILED",
                )

        logger.info(
            "Scheduled task cancelled: task_id=%s tenant=%s user=%s",
            task_id,
            runtime.user.tenant_id,
            runtime.user.user_id,
        )
        return ToolResult.success({"task_id": task_id, "status": "cancelled"})
    except Exception as e:
        logger.exception("Failed to cancel scheduled task")
        return ToolResult.error_result(
            f"Failed to cancel scheduled task: {e}",
            code="CANCEL_SCHEDULE_TASK_FAILED",
        )


class ListScheduledTasksSchema(BaseModel):
    status: str | None = Field(
        default=None,
        description="Filter by status: pending, running, paused, completed, failed, cancelled",
    )
    task_type: str | None = Field(
        default=None,
        description="Filter by task type: agent_run, skill_call, liveapp_job",
    )
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class GetScheduledTaskSchema(BaseModel):
    task_id: int = Field(..., gt=0)


@tool(args_schema=ListScheduledTasksSchema)
async def list_scheduled_tasks(
    config: RunnableConfig,
    status: str | None = None,
    task_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> ToolResult:
    """List scheduled tasks visible to the current user.

    Use this before `cancel_scheduled_task` or `update_scheduled_task` when the user
    refers to a task without providing `task_id`.
    """
    try:
        runtime = extract_runtime_context(config)
        async with app_db_session() as db_session:
            service = ScheduledTaskService.create(
                tenant_id=runtime.user.tenant_id,
                db_session=db_session,
            )
            rows = await service.list_tasks_for_actor(
                actor=_actor_ctx(runtime),
                status=status,
                task_type=task_type,
                limit=limit,
                offset=offset,
            )
        return ToolResult.success(
            {
                "tasks": [_task_payload(row) for row in rows],
                "count": len(rows),
                "limit": limit,
                "offset": offset,
            }
        )
    except Exception as e:
        logger.exception("Failed to list scheduled tasks")
        return ToolResult.error_result(
            f"Failed to list scheduled tasks: {e}",
            code="LIST_SCHEDULED_TASKS_FAILED",
        )


@tool(args_schema=GetScheduledTaskSchema)
async def get_scheduled_task(task_id: int, config: RunnableConfig) -> ToolResult:
    """Get details for a single scheduled task by ID."""
    try:
        runtime = extract_runtime_context(config)
        async with app_db_session() as db_session:
            service = ScheduledTaskService.create(
                tenant_id=runtime.user.tenant_id,
                db_session=db_session,
            )
            task = await service.get_task_for_actor(task_id=task_id, actor=_actor_ctx(runtime))
        return ToolResult.success(_task_payload(task))
    except ResourceNotFoundError as e:
        return ToolResult.error_result(str(e), code="SCHEDULED_TASK_NOT_FOUND")
    except Exception as e:
        logger.exception("Failed to get scheduled task")
        return ToolResult.error_result(
            f"Failed to get scheduled task: {e}",
            code="GET_SCHEDULED_TASK_FAILED",
        )
