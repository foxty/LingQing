"""DTO schemas for scheduled task services."""

from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel

from apps.shared.artifact.schemas import Artifact
from apps.shared.db.models import ScheduledTask


class ScheduledTaskResponseDTO(BaseModel):
    id: int
    name: str
    task_type: str
    task_config: dict
    schedule_type: str
    schedule_spec: dict
    status: str
    owner_name: str | None = None
    stable_key: str | None = None
    is_system: bool = False
    next_run_at: datetime | None
    last_run_at: datetime | None
    notification_channels: list[str] | None
    created_at: datetime
    updated_at: datetime


class TaskRunResultDTO(BaseModel):
    """Typed result payload for a task run.

    Log metadata fields are always present (when logs were persisted).
    The ``data`` dict holds task-type-specific output (sandbox stdout/stderr,
    agent_run execution_context, system handler result, etc.).
    """

    has_logs: bool = False
    stdout_log_path: str | None = None
    stderr_log_path: str | None = None
    data: dict = {}


class ScheduledTaskRunResponseDTO(BaseModel):
    id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None
    result: TaskRunResultDTO
    error_message: str | None


@dataclass
class ScheduledTaskCreateWithArtifactResult:
    """Result payload for scheduled task creation with artifact linkage."""

    task: ScheduledTask
    artifact: Artifact
