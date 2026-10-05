"""Message feedback router."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.message_feedback.schemas import (
    FeedbackListResponse,
    FeedbackResponse,
    FeedbackStatsResponse,
    SubmitFeedbackRequest,
    ThreadFeedbackMapResponse,
)
from apps.tenant_app_service.message_feedback.service import MessageFeedbackService

router = APIRouter(tags=["message-feedback"])

_ANALYSIS_PERMISSIONS = [Permissions.TENANT_ADMIN, Permissions.AGENTS_MANAGE]


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@router.put(
    "/threads/{thread_id}/messages/{message_id}/feedback",
    response_model=FeedbackResponse,
)
async def upsert_message_feedback(
    thread_id: str,
    message_id: str,
    request: SubmitFeedbackRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    service = MessageFeedbackService(current_user.tenant_id, db)
    return await service.upsert_feedback(
        thread_id=thread_id,
        message_id=message_id,
        user_id=current_user.id,
        rating=request.rating,
        comment=request.comment,
    )


@router.delete("/threads/{thread_id}/messages/{message_id}/feedback", status_code=204)
async def delete_message_feedback(
    thread_id: str,
    message_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    service = MessageFeedbackService(current_user.tenant_id, db)
    await service.delete_feedback(
        thread_id=thread_id,
        message_id=message_id,
        user_id=current_user.id,
    )


@router.get("/threads/{thread_id}/feedback", response_model=ThreadFeedbackMapResponse)
async def get_thread_feedback(
    thread_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    service = MessageFeedbackService(current_user.tenant_id, db)
    return await service.get_thread_feedback_map(thread_id=thread_id, user_id=current_user.id)


@router.get("/feedback/stats", response_model=FeedbackStatsResponse)
async def get_feedback_stats(
    agent_id: int | None = Query(None),
    source: str | None = Query(None),
    from_dt: str | None = Query(None, alias="from"),
    to_dt: str | None = Query(None, alias="to"),
    current_user: UserDTO = Depends(require_permission(_ANALYSIS_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
):
    service = MessageFeedbackService(current_user.tenant_id, db)
    return await service.get_stats(
        agent_id=agent_id,
        source=source,
        from_dt=_parse_dt(from_dt),
        to_dt=_parse_dt(to_dt),
    )


@router.get("/feedback", response_model=FeedbackListResponse)
async def list_feedback(
    agent_id: int | None = Query(None),
    rating: str | None = Query(None),
    source: str | None = Query(None),
    from_dt: str | None = Query(None, alias="from"),
    to_dt: str | None = Query(None, alias="to"),
    cursor: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserDTO = Depends(require_permission(_ANALYSIS_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
):
    service = MessageFeedbackService(current_user.tenant_id, db)
    return await service.list_feedback(
        agent_id=agent_id,
        rating=rating,
        source=source,
        from_dt=_parse_dt(from_dt),
        to_dt=_parse_dt(to_dt),
        cursor=cursor,
        limit=limit,
    )


@router.get("/feedback/export")
async def export_feedback(
    agent_id: int | None = Query(None),
    rating: str | None = Query(None),
    source: str | None = Query(None),
    from_dt: str | None = Query(None, alias="from"),
    to_dt: str | None = Query(None, alias="to"),
    current_user: UserDTO = Depends(require_permission(_ANALYSIS_PERMISSIONS)),
    db: AsyncSession = Depends(get_db),
):
    service = MessageFeedbackService(current_user.tenant_id, db)
    csv_content = await service.export_feedback_csv(
        agent_id=agent_id,
        rating=rating,
        source=source,
        from_dt=_parse_dt(from_dt),
        to_dt=_parse_dt(to_dt),
    )
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=message_feedback.csv"},
    )
