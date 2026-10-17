"""Authenticated chart image routes."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.chart.service import ChartService
from apps.shared.chart.storage import CHART_IMAGE_FORMAT_PNG, CHART_IMAGE_FORMAT_SVG, ChartImageFormat
from apps.shared.core.auth import get_current_user
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO

router = APIRouter(tags=["chart-media"])


def _actor(current_user: UserDTO) -> ActorContext:
    return ActorContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


@router.get("/charts/{chart_id}/image.{extension}")
async def get_chart_image(
    chart_id: int,
    extension: str,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fmt: ChartImageFormat = CHART_IMAGE_FORMAT_SVG
    if extension.lower() == "png":
        fmt = CHART_IMAGE_FORMAT_PNG
    service = ChartService.create(tenant_id=current_user.tenant_id, db=db)
    content, media_type = await service.read_image(
        chart_id,
        fmt=fmt,
        actor=_actor(current_user),
    )
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})
