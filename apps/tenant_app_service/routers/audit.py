"""Tenant audit log query and export."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.audit_event.context import AuditRequestContext
from apps.shared.audit_event.repository import DEFAULT_PAGE_SIZE
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.audit.service import TenantAuditQueryService, iter_audit_export_csv

router = APIRouter(prefix="/audit", tags=["audit"])


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@router.get("/events")
async def list_audit_events(
    actor_user_id: int | None = Query(None),
    event_type: str | None = Query(None),
    from_dt: str | None = Query(None, alias="from"),
    to_dt: str | None = Query(None, alias="to"),
    page: int = Query(1, ge=1),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=100),
    current_user: UserDTO = Depends(require_permission(Permissions.AUDIT_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = TenantAuditQueryService(current_user.tenant_id, db)
    return await service.list_events(
        actor_user_id=actor_user_id,
        event_type=event_type,
        from_dt=_parse_dt(from_dt),
        to_dt=_parse_dt(to_dt),
        page=page,
        page_size=page_size,
    )


@router.get("/events/export")
async def export_audit_events(
    request: Request,
    actor_user_id: int | None = Query(None),
    event_type: str | None = Query(None),
    from_dt: str | None = Query(None, alias="from"),
    to_dt: str | None = Query(None, alias="to"),
    current_user: UserDTO = Depends(require_permission(Permissions.AUDIT_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    ctx = AuditRequestContext.from_request(request)
    parsed_from = _parse_dt(from_dt)
    parsed_to = _parse_dt(to_dt)
    filter_summary = {
        k: v
        for k, v in {
            "actor_user_id": actor_user_id,
            "event_type": event_type,
            "from": from_dt,
            "to": to_dt,
        }.items()
        if v is not None
    }

    service = TenantAuditQueryService(current_user.tenant_id, db)
    stats = await service.export_stats(
        actor_user_id=actor_user_id,
        event_type=event_type,
        from_dt=parsed_from,
        to_dt=parsed_to,
    )

    return StreamingResponse(
        iter_audit_export_csv(
            current_user.tenant_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            from_dt=parsed_from,
            to_dt=parsed_to,
            actor_context_user_id=current_user.id,
            request_context=ctx,
            filter_summary=filter_summary,
            stats=stats,
        ),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=audit_events.csv",
            "X-Audit-Truncated": "true" if stats.truncated else "false",
            "X-Audit-Total-Matched": str(stats.total_matched),
            "X-Audit-Exported-Count": str(stats.exported_count),
        },
    )