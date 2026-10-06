"""Agent-scoped Slack integration admin routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.auth import get_current_user, require_permission
from apps.shared.core.exceptions import AuthorizationError
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ, ABAC_ACTION_WRITE
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID
from apps.tenant_app_service.agent_catalog.services import AgentCatalogService
from apps.tenant_app_service.agent_ingress.slack.admin_service import SlackAdminService
from apps.tenant_app_service.agent_ingress.slack.dtos import (
    CreateAgentSlackIntegrationRequest,
    SlackIntegrationResponse,
    SlackTestConnectionResponse,
    UpdateAgentSlackIntegrationRequest,
)

router = APIRouter(prefix="/agents/{agent_id}/integrations/slack", tags=["slack"])


def _actor(user: UserDTO) -> ActorContext:
    return ActorContext(tenant_id=user.tenant_id, user_id=user.id, user_role=user.role)


async def _ensure_agent_slack_read(
    agent_id: int,
    current_user: UserDTO,
    db: AsyncSession,
) -> None:
    if agent_id == SYSTEM_AGENT_ONE_ID:
        return
    catalog = AgentCatalogService(tenant_id=current_user.tenant_id, db_session=db)
    await catalog.require_agent_access(
        agent_id=agent_id,
        actor=_actor(current_user),
        action=ABAC_ACTION_READ,
    )


async def _ensure_agent_slack_write(
    agent_id: int,
    current_user: UserDTO,
    db: AsyncSession,
) -> None:
    if agent_id == SYSTEM_AGENT_ONE_ID:
        allowed = await role_has_permission(
            db,
            current_user.tenant_id,
            current_user.role,
            Permissions.AUTH_PROVIDERS_MANAGE,
        )
        if not allowed:
            raise AuthorizationError("Insufficient permissions to manage built-in agent Slack")
        return
    allowed = await role_has_permission(
        db,
        current_user.tenant_id,
        current_user.role,
        Permissions.AGENTS_WRITE,
    )
    if not allowed:
        raise AuthorizationError("Insufficient permissions to manage agent Slack")
    catalog = AgentCatalogService(tenant_id=current_user.tenant_id, db_session=db)
    await catalog.require_agent_access(
        agent_id=agent_id,
        actor=_actor(current_user),
        action=ABAC_ACTION_WRITE,
    )


async def _require_agent_slack_write(
    agent_id: int,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> tuple[UserDTO, AsyncSession]:
    await _ensure_agent_slack_write(agent_id, current_user, db)
    return current_user, db


@router.get(
    "",
    response_model=SlackIntegrationResponse,
    responses={status.HTTP_204_NO_CONTENT: {"description": "Slack integration not configured for this agent"}},
)
async def get_agent_slack_integration(
    agent_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_agent_slack_read(agent_id, current_user, db)
    service = SlackAdminService(db)
    result = await service.get_integration_optional(current_user.tenant_id, agent_id)
    if result is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return result


@router.post("/prepare", response_model=SlackIntegrationResponse)
async def prepare_agent_slack_integration(
    agent_id: int,
    auth: tuple[UserDTO, AsyncSession] = Depends(_require_agent_slack_write),
):
    current_user, db = auth
    service = SlackAdminService(db)
    await service.ensure_provisioned_endpoint(current_user.tenant_id, agent_id)
    await db.commit()
    integration = await service.get_integration(current_user.tenant_id, agent_id)
    return integration


@router.get("/manifest")
async def download_agent_slack_app_manifest(
    agent_id: int,
    auth: tuple[UserDTO, AsyncSession] = Depends(_require_agent_slack_write),
):
    current_user, db = auth
    service = SlackAdminService(db)
    endpoint = await service.ensure_provisioned_endpoint(current_user.tenant_id, agent_id)
    await db.commit()
    manifest = await service.build_app_manifest_for_agent(
        current_user.tenant_id,
        agent_id,
        endpoint.endpoint_key,
    )
    filename = f"lingqing-slack-manifest-agent-{agent_id}.json"
    return Response(
        content=json.dumps(manifest, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "",
    response_model=SlackIntegrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_slack_integration(
    agent_id: int,
    request: CreateAgentSlackIntegrationRequest,
    auth: tuple[UserDTO, AsyncSession] = Depends(_require_agent_slack_write),
):
    current_user, db = auth
    service = SlackAdminService(db)
    result = await service.create_integration(current_user.tenant_id, agent_id, request)
    await db.commit()
    return result


@router.patch("", response_model=SlackIntegrationResponse)
async def update_agent_slack_integration(
    agent_id: int,
    request: UpdateAgentSlackIntegrationRequest,
    auth: tuple[UserDTO, AsyncSession] = Depends(_require_agent_slack_write),
):
    current_user, db = auth
    service = SlackAdminService(db)
    result = await service.update_integration(current_user.tenant_id, agent_id, request)
    await db.commit()
    return result


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_slack_integration(
    agent_id: int,
    auth: tuple[UserDTO, AsyncSession] = Depends(_require_agent_slack_write),
):
    current_user, db = auth
    service = SlackAdminService(db)
    await service.delete_integration(current_user.tenant_id, agent_id)
    await db.commit()


@router.post("/enable", response_model=SlackIntegrationResponse)
async def enable_agent_slack_integration(
    agent_id: int,
    auth: tuple[UserDTO, AsyncSession] = Depends(_require_agent_slack_write),
):
    current_user, db = auth
    service = SlackAdminService(db)
    result = await service.set_enabled(current_user.tenant_id, agent_id, True)
    await db.commit()
    return result


@router.post("/disable", response_model=SlackIntegrationResponse)
async def disable_agent_slack_integration(
    agent_id: int,
    auth: tuple[UserDTO, AsyncSession] = Depends(_require_agent_slack_write),
):
    current_user, db = auth
    service = SlackAdminService(db)
    result = await service.set_enabled(current_user.tenant_id, agent_id, False)
    await db.commit()
    return result


@router.post("/test", response_model=SlackTestConnectionResponse)
async def test_agent_slack_connection(
    agent_id: int,
    auth: tuple[UserDTO, AsyncSession] = Depends(_require_agent_slack_write),
):
    current_user, db = auth
    service = SlackAdminService(db)
    result = await service.test_connection(current_user.tenant_id, agent_id)
    if result.ok:
        await db.commit()
    return result
