"""Admin APIs for platform-managed system scheduled tasks."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.auth import require_tenant_admin
from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.pagination import PaginatedResponse
from apps.shared.schemas.user import UserDTO
from apps.shared.tasks.adapters import scheduled_task_to_response_payload
from apps.shared.tasks.schemas import ScheduledTaskResponseDTO, ScheduledTaskRunResponseDTO
from apps.shared.tasks.service import ScheduledTaskService

router = APIRouter(prefix="/admin/system-tasks", tags=["admin-system-tasks"])


def _actor_ctx(current_user: UserDTO) -> ActorContext:
    return ActorContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


@router.get("", response_model=list[ScheduledTaskResponseDTO])
async def list_system_tasks(
    status: str | None = Query(None),
    task_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: UserDTO = Depends(require_tenant_admin()),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    rows = await service.list_system_tasks_for_admin(
        actor=actor,
        status=status,
        task_type=task_type,
        limit=limit,
        offset=offset,
    )
    return [scheduled_task_to_response_payload(row) for row in rows]


@router.get("/{task_id}", response_model=ScheduledTaskResponseDTO)
async def get_system_task(
    task_id: int,
    current_user: UserDTO = Depends(require_tenant_admin()),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    row = await service.get_system_task_for_admin(task_id=task_id, actor=actor)
    return scheduled_task_to_response_payload(row)


@router.get("/{task_id}/runs", response_model=PaginatedResponse[ScheduledTaskRunResponseDTO])
async def list_system_task_runs(
    task_id: int,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: UserDTO = Depends(require_tenant_admin()),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    dtos, pagination = await service.list_system_task_runs_for_admin(
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
async def get_system_task_run_logs(
    task_id: int,
    run_id: int,
    stream: Literal["stdout", "stderr"] = Query("stdout", description="Log stream: 'stdout' or 'stderr'"),
    current_user: UserDTO = Depends(require_tenant_admin()),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    content = await service.get_system_run_log_content_for_admin(
        task_id=task_id,
        run_id=run_id,
        stream=stream,
        actor=actor,
    )
    return PlainTextResponse(content=content)


@router.patch("/{task_id}/pause")
async def pause_system_task(
    task_id: int,
    current_user: UserDTO = Depends(require_tenant_admin()),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    ok = await service.pause_system_task_for_admin(task_id=task_id, actor=actor)
    if not ok:
        raise ResourceNotFoundError(f"System task not found or cannot be paused: {task_id}")
    await db.commit()
    return {"message": "System task paused"}


@router.patch("/{task_id}/resume")
async def resume_system_task(
    task_id: int,
    current_user: UserDTO = Depends(require_tenant_admin()),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    ok = await service.resume_system_task_for_admin(task_id=task_id, actor=actor)
    if not ok:
        raise ResourceNotFoundError(f"System task cannot be resumed: {task_id}")
    await db.commit()
    return {"message": "System task resumed"}


@router.patch("/{task_id}/run")
async def run_system_task(
    task_id: int,
    current_user: UserDTO = Depends(require_tenant_admin()),
    db: AsyncSession = Depends(get_db),
):
    actor = _actor_ctx(current_user)
    service = ScheduledTaskService.create(tenant_id=actor.tenant_id, db_session=db)
    ok = await service.run_system_task_for_admin(task_id=task_id, actor=actor)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="System task cannot be run (must be pending or paused, and not already running)",
        )
    await db.commit()
    return {"message": "System task queued for immediate execution"}
