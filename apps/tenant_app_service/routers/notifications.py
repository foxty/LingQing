"""Notification inbox and preference APIs."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.db.session import get_db
from apps.shared.notification.repository import NotificationPreferenceRepository, NotificationRepository
from apps.shared.notification.schemas import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdateRequest,
    NotificationResponse,
)
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    is_read: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    repo = NotificationRepository(db)
    rows = await repo.list_notifications(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        is_read=is_read,
        limit=limit,
        offset=offset,
    )
    return [
        NotificationResponse(
            id=row.id,
            event_type=row.event_type,
            title=row.title,
            payload=row.payload,
            is_read=row.is_read,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    repo = NotificationRepository(db)
    ok = await repo.mark_as_read(
        notification_id=notification_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    if not ok:
        raise ResourceNotFoundError(f"Notification not found: {notification_id}")
    await db.commit()
    return {"message": "Notification marked as read"}


@router.patch("/read-all")
async def mark_all_notifications_read(
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    repo = NotificationRepository(db)
    count = await repo.mark_all_as_read(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    await db.commit()
    return {"message": "Notifications marked as read", "count": count}


@router.get("/preferences", response_model=list[NotificationPreferenceResponse])
async def get_notification_preferences(
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    repo = NotificationPreferenceRepository(db)
    rows = await repo.get_user_preferences(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
    )
    return [
        NotificationPreferenceResponse(
            event_type=row.event_type,
            channels=row.channels,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.put("/preferences", response_model=list[NotificationPreferenceResponse])
async def update_notification_preferences(
    request: NotificationPreferenceUpdateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    repo = NotificationPreferenceRepository(db)
    updated = []
    for pref in request.preferences:
        row = await repo.upsert_user_preference(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            event_type=pref.event_type.strip(),
            channels=pref.channels,
        )
        updated.append(row)
    await db.commit()
    return [
        NotificationPreferenceResponse(
            event_type=row.event_type,
            channels=row.channels,
            updated_at=row.updated_at,
        )
        for row in updated
    ]
