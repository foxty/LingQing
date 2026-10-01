"""Domain models for unified scheduled tasks."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, NotRequired, get_args

from typing_extensions import TypedDict

from apps.shared.domain.base_domain_model import BaseDomainModel

TASK_TYPE_AGENT_RUN = "agent_run"
TASK_TYPE_SKILL_CALL = "skill_call"
TASK_TYPE_LIVEAPP_JOB = "liveapp_job"
TASK_TYPE_SYSTEM = "system"
ScheduledTaskType = Literal["agent_run", "skill_call", "liveapp_job", "system"]

# Task origin (scheduled_tasks.source_type) — see DB column comment
SOURCE_TYPE_AGENT = "agent"
SOURCE_TYPE_SYSTEM = "system"
SOURCE_TYPE_LIVEAPP = "liveapp"
SOURCE_TYPE_SKILL = "skill"
ScheduledTaskSourceType = Literal["agent", "system", "liveapp", "skill"]


def is_system_scheduled_task(task) -> bool:
    """Return True for platform-managed tasks seeded by the system reconciler.

    Uses ``stable_key``, not ``task_type``, because:
    - ``task_type=system`` only describes execution strategy (internal handler dispatch)
    - ``stable_key`` is the reconciler's idempotent ownership key and the auth-split boundary
    - user-created tasks never get a stable_key; reconciler rows always do
    """
    return bool(getattr(task, "stable_key", None))


ALL_SCHEDULED_TASK_TYPES: tuple[str, ...] = get_args(ScheduledTaskType)

# Execution modes
EXECUTION_MODE_INTERNAL = "internal"
EXECUTION_MODE_SANDBOX = "sandbox"
ExecutionMode = Literal["internal", "sandbox"]

SCHEDULE_TYPE_ONCE = "once"
SCHEDULE_TYPE_CRON = "cron"
ScheduledTaskScheduleType = Literal["once", "cron"]
ALL_SCHEDULE_TYPES: tuple[str, ...] = get_args(ScheduledTaskScheduleType)

TASK_STATUS_PENDING = "pending"
TASK_STATUS_RUNNING = "running"
TASK_STATUS_COMPLETED = "completed"
TASK_STATUS_FAILED = "failed"
TASK_STATUS_PAUSED = "paused"
TASK_STATUS_CANCELLED = "cancelled"
ScheduledTaskStatus = Literal["pending", "running", "completed", "failed", "paused", "cancelled"]
ACTIVE_TASK_STATUSES: tuple[ScheduledTaskStatus, ...] = (
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    TASK_STATUS_PAUSED,
)

TASK_RUN_STATUS_RUNNING = "running"
TASK_RUN_STATUS_SUCCESS = "success"
TASK_RUN_STATUS_FAILED = "failed"

SCHEDULED_TASK_NAME_MAX_LENGTH = 120


class AgentRunTaskConfig(TypedDict, total=False):
    """Task config for agent_run task type.

    All fields are optional - missing values are auto-filled from runtime context.
    """

    agent_id: NotRequired[int]
    task_description: NotRequired[str]
    origin_thread_id: NotRequired[str]


class SkillCallTaskConfig(TypedDict, total=False):
    """Task config for skill_call task type."""

    skill_id: str
    entrypoint: str
    skill_input_params: dict[str, Any]


class LiveAppJobTaskConfig(TypedDict, total=False):
    """Task config for liveapp_job task type (replaces etl_job)."""

    app_id: int
    job_name: str  # e.g., "sync_external_api", "daily_aggregation"
    entrypoint: str  # relative path like "jobs/sync_external_api.py"
    job_params: dict[str, Any]
    environment: str  # dev, test, or prod


class SystemTaskConfig(TypedDict, total=False):
    """Task config for system tasks (internal use only, never created via agent tools)."""

    handler_ref: str  # Fully-qualified 'module:function' path


TaskConfig = AgentRunTaskConfig | SkillCallTaskConfig | LiveAppJobTaskConfig | SystemTaskConfig


@dataclass
class SandboxExecutionParams:
    """Execution parameters for sandbox tasks."""

    target_id: str
    entrypoint: str
    command_template: str


class TaskExecutionContext(TypedDict):
    """Tenant-scoped runtime context for a single scheduled task execution."""

    task_id: int
    tenant_id: int
    user_id: int | None
    input_params: dict[str, Any]


class OnceScheduleSpec(TypedDict):
    """Schedule spec for once tasks."""

    run_at: str


class CronScheduleSpec(TypedDict):
    """Schedule spec for cron tasks."""

    cron: str
    timezone: NotRequired[str]


ScheduleSpec = OnceScheduleSpec | CronScheduleSpec


def normalize_scheduled_task_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValueError("task name cannot be empty")
    return stripped[:SCHEDULED_TASK_NAME_MAX_LENGTH]


def is_valid_scheduled_task_type(task_type: str) -> bool:
    return task_type in ALL_SCHEDULED_TASK_TYPES


def is_valid_schedule_type(schedule_type: str) -> bool:
    return schedule_type in ALL_SCHEDULE_TYPES


def normalize_agent_run_task_config(task_config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(task_config)
    normalized.pop("thread_mode", None)
    return normalized


def parse_agent_run_task_config(task_config: dict[str, Any]) -> AgentRunTaskConfig:
    agent_id = task_config.get("agent_id")
    task_description = task_config.get("task_description")

    if not isinstance(agent_id, int):
        raise ValueError("task_config.agent_id is required for agent_run")
    if not isinstance(task_description, str) or not task_description.strip():
        raise ValueError("task_config.task_description is required for agent_run")

    parsed: AgentRunTaskConfig = {
        "agent_id": agent_id,
        "task_description": task_description,
    }

    origin_thread_id = task_config.get("origin_thread_id")
    if isinstance(origin_thread_id, str) and origin_thread_id:
        parsed["origin_thread_id"] = origin_thread_id

    return parsed


@dataclass
class ScheduledTaskDomain(BaseDomainModel):
    """Domain model for user-configurable scheduled tasks."""

    id: int
    tenant_id: int
    user_id: int
    name: str
    task_type: ScheduledTaskType
    task_config: TaskConfig
    schedule_type: ScheduledTaskScheduleType
    schedule_spec: ScheduleSpec
    status: ScheduledTaskStatus
    next_run_at: datetime | None
    last_run_at: datetime | None
    notification_channels: list[str] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    input_params: dict[str, Any] | None = None

    def get_sandbox_execution_params(self) -> SandboxExecutionParams | None:
        """Get sandbox execution parameters if this task runs in sandbox.

        Returns typed SandboxExecutionParams, or None for internal tasks.
        This encapsulates the routing logic that maps task_type to execution strategy.
        """
        if self.task_type == TASK_TYPE_SKILL_CALL:
            skill_id = (self.task_config or {}).get("skill_id", "")
            entrypoint = (self.task_config or {}).get("entrypoint", "")
            module = entrypoint.split(":")[0] if ":" in entrypoint else entrypoint
            return SandboxExecutionParams(
                target_id=skill_id,
                entrypoint=entrypoint,
                command_template=f"python -m {module}",
            )
        elif self.task_type == TASK_TYPE_LIVEAPP_JOB:
            app_id = (self.task_config or {}).get("app_id", 0)
            job_name = (self.task_config or {}).get("job_name", "")
            entrypoint = (self.task_config or {}).get("entrypoint", "")
            # Sandbox execution setup (transparent to job script):
            # 1. cd /app_root — working directory for relative imports
            # 2. pip install -r requirements.txt — install app dependencies to .venv (persisted across runs)
            # 3. PYTHONPATH includes .venv — make installed packages importable
            # Job script only needs: from lingqing_sdk import LiveAppClient
            command_template = (
                f"cd /app_root && "
                f"if [ -f requirements.txt ]; then "
                f"mkdir -p .venv && "
                f"pip install -q --cache-dir /tmp/pip-cache --target .venv -r requirements.txt && "
                f"export PYTHONPATH=/app_root:/app_root/.venv:$PYTHONPATH; "
                f"fi && "
                f"python {entrypoint}"
            )
            return SandboxExecutionParams(
                target_id=f"{app_id}:{job_name}",
                entrypoint=entrypoint,
                command_template=command_template,
            )
        else:
            # Internal execution (agent_run, system) - no sandbox params
            return None
