"""Unified scheduled task management APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.auth import get_current_user
from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.pagination import PaginatedResponse
from apps.shared.schemas.user import UserDTO
from apps.shared.tasks.adapters import scheduled_task_to_response_payload
from apps.shared.tasks.schemas import ScheduledTaskResponseDTO, ScheduledTaskRunResponseDTO
from apps.shared.tasks.service import ScheduledTaskService

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


def _actor_ctx(current_user: UserDTO) -> ActorContext:
    return ActorContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


@router.get("", response_model=list[ScheduledTaskResponseDTO])
async def list_scheduled_tasks(
    status: str | None = Query(None),
    task_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    rows = await service.list_tasks_for_actor(
        actor=actor,
        status=status,
        task_type=task_type,
        limit=limit,
        offset=offset,
    )
    return [scheduled_task_to_response_payload(row) for row in rows]


@router.get("/{task_id}", response_model=ScheduledTaskResponseDTO)
async def get_scheduled_task(
    task_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    row = await service.get_task_for_actor(task_id=task_id, actor=actor)
    return scheduled_task_to_response_payload(row)


@router.get("/{task_id}/runs", response_model=PaginatedResponse[ScheduledTaskRunResponseDTO])
async def list_scheduled_task_runs(
    task_id: int,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    dtos, pagination = await service.list_task_runs_for_actor(
        task_id=task_id,
        actor=actor,
        page=page,
        page_size=page_size,
    )

    return PaginatedResponse(
        items=dtos,
        total=pagination.total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=pagination.total_pages,
    )


@router.get("/{task_id}/runs/{run_id}/logs")
async def get_task_run_logs(
    task_id: int,
    run_id: int,
    stream: str = Query("stdout", description="Log stream: 'stdout' or 'stderr'"),
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream log content for a specific task run.

    Returns plain text log content. Returns 404 if no logs exist.
    """
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    content = await service.get_run_log_content(
        task_id=task_id,
        run_id=run_id,
        stream=stream,
        actor=actor,
    )
    return PlainTextResponse(content=content)


@router.patch("/{task_id}/cancel")
async def cancel_scheduled_task(
    task_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    ok = await service.cancel_task_for_actor(task_id=task_id, actor=actor)
    if not ok:
        raise ResourceNotFoundError(f"Scheduled task not found or cannot be cancelled: {task_id}")
    await db.commit()
    return {"message": "Scheduled task cancelled"}


@router.patch("/{task_id}/pause")
async def pause_scheduled_task(
    task_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    ok = await service.pause_task_for_actor(task_id=task_id, actor=actor)
    if not ok:
        raise ResourceNotFoundError(f"Scheduled task not found or cannot be paused: {task_id}")
    await db.commit()
    return {"message": "Scheduled task paused"}


@router.patch("/{task_id}/resume")
async def resume_scheduled_task(
    task_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    ok = await service.resume_task_for_actor(task_id=task_id, actor=actor)
    if not ok:
        raise ResourceNotFoundError(f"Scheduled task cannot be resumed: {task_id}")
    await db.commit()
    return {"message": "Scheduled task queued for immediate execution"}


@router.patch("/{task_id}/run")
async def run_scheduled_task(
    task_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    ok = await service.run_task_for_actor(task_id=task_id, actor=actor)
    if not ok:
        raise HTTPException(
            status_code=400, detail="Task cannot be run (must be pending or paused, and not already running)"
        )
    await db.commit()
    return {"message": "Scheduled task queued for immediate execution"}


@router.delete("/{task_id}")
async def delete_scheduled_task(
    task_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    ok = await service.delete_task_for_actor(task_id=task_id, actor=actor)
    if not ok:
        raise ResourceNotFoundError(f"Scheduled task not found: {task_id}")
    await db.commit()
    return {"message": "Scheduled task deleted"}
