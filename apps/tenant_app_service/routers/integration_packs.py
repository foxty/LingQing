"""API connector pack catalog and installation routes."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.api_connector.schemas import ApiConnectorResponse
from apps.shared.external_systems.packs.schemas import (
    ApiConnectorPackListResponse,
    InstallApiConnectorPackRequest,
)
from apps.shared.external_systems.packs.service import ApiConnectorPackService
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/integration-packs", tags=["integration-packs"])


def _actor(user: UserDTO) -> ActorContext:
    return ActorContext(tenant_id=user.tenant_id, user_id=user.id, user_role=user.role)


@router.get("", response_model=ApiConnectorPackListResponse)
async def list_api_connector_packs(
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.API_CONNECTORS_READ)),
):
    service = ApiConnectorPackService(current_user.tenant_id, db)
    return ApiConnectorPackListResponse(items=service.list_packs())


@router.post(
    "/install",
    response_model=ApiConnectorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def install_api_connector_pack(
    body: InstallApiConnectorPackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.API_CONNECTORS_CREATE)),
):
    service = ApiConnectorPackService(current_user.tenant_id, db)
    return await service.install(actor=_actor(current_user), request=body)
