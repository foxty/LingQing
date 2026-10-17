"""Chart read authorization (artifact ACL + transitive report embed)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.access import ArtifactAccessGuard
from apps.shared.artifact.domain import ArtifactType
from apps.shared.chart.embed import EMBEDDED_CHART_IDS_METADATA_KEY
from apps.shared.chart.repository import ChartRepository
from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.shared.domain.actor import ActorContext


async def require_chart_read_access(
    *,
    db: AsyncSession,
    tenant_id: int,
    actor: ActorContext,
    chart_id: int,
) -> None:
    repo = ChartRepository(db)
    chart = await repo.get_by_id(chart_id, tenant_id=tenant_id)
    if chart is None:
        raise ResourceNotFoundError("Chart not found")
    guard = ArtifactAccessGuard(
        db=db,
        tenant_id=actor.tenant_id,
        user_id=actor.user_id,
        user_role=actor.user_role,
        artifact_type=ArtifactType.CHART.value,
    )
    try:
        await guard.require_read(resource_id=chart_id)
        return
    except AuthorizationError:
        if await _can_read_via_report_embed(db=db, tenant_id=tenant_id, actor=actor, chart_id=chart_id):
            return
        raise


async def validate_embedded_chart_ids(
    *,
    db: AsyncSession,
    tenant_id: int,
    actor: ActorContext,
    chart_ids: list[int],
) -> None:
    for chart_id in chart_ids:
        await require_chart_read_access(db=db, tenant_id=tenant_id, actor=actor, chart_id=chart_id)


async def _can_read_via_report_embed(
    *,
    db: AsyncSession,
    tenant_id: int,
    actor: ActorContext,
    chart_id: int,
) -> bool:
    from apps.shared.report.repository import ReportRepository

    report_repo = ReportRepository(db)
    reports = await report_repo.list_for_user_access(
        tenant_id=tenant_id,
        user_id=actor.user_id,
        limit=500,
        offset=0,
    )
    report_guard = ArtifactAccessGuard(
        db=db,
        tenant_id=actor.tenant_id,
        user_id=actor.user_id,
        user_role=actor.user_role,
        artifact_type=ArtifactType.REPORT.value,
    )
    for report in reports:
        meta = report.report_metadata or {}
        embedded = meta.get(EMBEDDED_CHART_IDS_METADATA_KEY) or []
        if chart_id not in embedded:
            continue
        try:
            await report_guard.require_read(resource_id=report.id)
            return True
        except AuthorizationError:
            continue
    return False
