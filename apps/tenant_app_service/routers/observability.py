"""Observability router."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.exceptions import ValidationError
from apps.shared.db.session import get_db
from apps.shared.observability.dtos import TenantUsageStatsDTO
from apps.shared.observability.service import ObservabilityService
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.tenant.schemas import TokenUsageDailyPoint, TokenUsageEventsResponse

router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/tenant/token-summary", response_model=TenantUsageStatsDTO)
async def get_tenant_token_summary(
    days: int = Query(default=30, ge=1, le=90),
    user_id: int | None = Query(default=None),
    agent_id: int | None = Query(default=None),
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant token usage summary for a time window."""
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=days)

    service = ObservabilityService.create(db, current_user.tenant_id)
    return await service.get_tenant_usage_stats(
        tenant_id=current_user.tenant_id,
        start_time=period_start,
        end_time=period_end,
        user_id=user_id,
        agent_id=agent_id,
    )


@router.get("/tenant/token-daily", response_model=list[TokenUsageDailyPoint])
async def get_tenant_token_daily(
    days: int = Query(default=30, ge=1, le=90),
    user_id: int | None = Query(default=None),
    agent_id: int | None = Query(default=None),
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant daily token trend for a time window."""
    period_end = datetime.now(UTC)
    period_start = period_end - timedelta(days=days)

    service = ObservabilityService.create(db, current_user.tenant_id)
    rows = await service.get_tenant_token_daily_usage(
        tenant_id=current_user.tenant_id,
        start_time=period_start,
        end_time=period_end,
        user_id=user_id,
        agent_id=agent_id,
    )
    return [TokenUsageDailyPoint(**row) for row in rows]


@router.get("/tenant/token-events", response_model=TokenUsageEventsResponse)
async def get_tenant_token_events(
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_id: int | None = Query(default=None),
    agent_id: int | None = Query(default=None),
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get paginated tenant token event records."""
    if page < 1:
        raise ValidationError("page must be >= 1")
    if page_size < 1 or page_size > 100:
        raise ValidationError("page_size must be between 1 and 100")

    period_end = end_time or datetime.now(UTC)
    period_start = start_time or (period_end - timedelta(days=7))

    service = ObservabilityService.create(db, current_user.tenant_id)
    total, rows = await service.get_tenant_token_events(
        tenant_id=current_user.tenant_id,
        start_time=period_start,
        end_time=period_end,
        page=page,
        page_size=page_size,
        user_id=user_id,
        agent_id=agent_id,
    )

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return TokenUsageEventsResponse(
        page=page,
        page_size=page_size,
        total=total,
        total_pages=total_pages,
        rows=rows,
    )
