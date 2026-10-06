"""Slack integration listing (tenant-scoped admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agent_ingress.slack.admin_service import SlackAdminService
from apps.tenant_app_service.agent_ingress.slack.dtos import SlackIntegrationResponse

router = APIRouter(tags=["slack"], include_in_schema=False)


@router.get("/integrations/slack/endpoints", response_model=list[SlackIntegrationResponse])
async def list_slack_integrations(
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = SlackAdminService(db)
    return await service.list_integrations(current_user.tenant_id)
