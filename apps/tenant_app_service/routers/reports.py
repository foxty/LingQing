"""Report API routes.

Provides durable report resources that remain available even if the originating
thread is deleted. Access control for collaboration uses the artifacts API
(`/artifacts/{id}/shares`).
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.auth import get_current_user
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.report.schemas import ReportResponse
from apps.shared.report.service import ReportService
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/reports", tags=["reports"])


def _actor_ctx(current_user: UserDTO) -> ActorContext:
    return ActorContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


@router.get("", response_model=list[ReportResponse])
async def list_my_reports(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReportService.create(tenant_id=current_user.tenant_id, db_session=db)
    reports = await service.list_reports_for_actor(
        actor=_actor_ctx(current_user),
        limit=limit,
        offset=offset,
    )
    return reports


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReportService.create(tenant_id=current_user.tenant_id, db_session=db)
    report = await service.get_report_for_actor(report_id, actor=_actor_ctx(current_user))
    return report


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ReportService.create(tenant_id=current_user.tenant_id, db_session=db)
    await service.delete_report_for_actor(
        report_id=report_id,
        actor=_actor_ctx(current_user),
    )
    await db.commit()
