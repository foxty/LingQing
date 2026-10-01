"""Adapters for scheduled task transport payloads and model conversion."""

from typing import Any

from apps.shared.tasks.domain import ScheduledTaskDomain, is_system_scheduled_task
from apps.shared.tasks.schemas import (
    ScheduledTaskResponseDTO,
    ScheduledTaskRunResponseDTO,
    TaskRunResultDTO,
)


def db_task_to_domain(db_task: Any) -> ScheduledTaskDomain:
    """Adapter: Convert DB model to domain model.

    This adapter maintains Clean Architecture boundaries by keeping
    DB-to-domain conversion in the infrastructure layer.

    Args:
        db_task: ScheduledTask SQLAlchemy model instance or compatible object

    Returns:
        ScheduledTaskDomain instance with business logic methods
    """
    return ScheduledTaskDomain(
        id=db_task.id,
        tenant_id=db_task.tenant_id,
        user_id=db_task.user_id,
        name=db_task.name,
        task_type=db_task.task_type,
        task_config=getattr(db_task, "task_config", {}) or {},
        input_params=getattr(db_task, "input_params", None),
        schedule_type=db_task.schedule_type,
        schedule_spec=getattr(db_task, "schedule_spec", {}) or {},
        status=db_task.status,
        next_run_at=getattr(db_task, "next_run_at", None),
        last_run_at=getattr(db_task, "last_run_at", None),
        notification_channels=getattr(db_task, "notification_channels", None),
        error_message=getattr(db_task, "error_message", None),
        created_at=getattr(db_task, "created_at", None),
        updated_at=getattr(db_task, "updated_at", None),
    )


def scheduled_task_to_response_payload(row: Any) -> ScheduledTaskResponseDTO:
    """Convert a scheduled task row/model into API response DTO.

    Keeps owner display name derivation in shared adapter layer so routers remain thin.
    """
    owner_name = (
        row.owner_user.username
        if getattr(row, "owner_user", None)
        else "已删除用户"
        if getattr(row, "owner_id", None) is not None
        else None
    )

    stable_key = getattr(row, "stable_key", None)
    payload = ScheduledTaskResponseDTO(
        id=row.id,
        name=row.name,
        task_type=row.task_type,
        task_config=row.task_config,
        schedule_type=row.schedule_type,
        schedule_spec=row.schedule_spec,
        status=row.status,
        owner_name=owner_name,
        stable_key=stable_key,
        is_system=is_system_scheduled_task(row),
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        notification_channels=row.notification_channels,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return payload


# Keys reserved for log metadata — excluded from TaskRunResultDTO.data
_LOG_METADATA_KEYS = frozenset({"has_logs", "stdout_log_path", "stderr_log_path"})


def _build_task_run_result_dto(raw_result: dict[str, Any] | None) -> TaskRunResultDTO:
    """Convert raw result dict into typed TaskRunResultDTO.

    Extracts log metadata fields; everything else goes into ``data``.
    """
    result = raw_result or {}
    has_logs = bool(result.get("has_logs"))
    stdout_log_path = result.get("stdout_log_path")
    stderr_log_path = result.get("stderr_log_path")
    data = {k: v for k, v in result.items() if k not in _LOG_METADATA_KEYS}

    return TaskRunResultDTO(
        has_logs=has_logs,
        stdout_log_path=stdout_log_path,
        stderr_log_path=stderr_log_path,
        data=data,
    )


def scheduled_task_run_to_response_dto(row: Any) -> ScheduledTaskRunResponseDTO:
    """Convert a TaskRun DB row into ScheduledTaskRunResponseDTO."""
    raw_result = getattr(row, "result", None) or {}
    result_dto = _build_task_run_result_dto(raw_result)

    return ScheduledTaskRunResponseDTO(
        id=row.id,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=row.duration_ms,
        result=result_dto,
        error_message=row.error_message,
    )


# Keep backward-compatible alias for callers using the old name
scheduled_task_run_to_response_payload = scheduled_task_run_to_response_dto
