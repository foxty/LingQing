"""API connector pack catalog and installation routes."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.api_connector.schemas import InstallPackOAuthInput
from apps.shared.external_systems.api_connector.service import ApiConnectorService
from apps.shared.external_systems.packs.loader import ApiConnectorPackCatalog
from apps.shared.external_systems.packs.schemas import (
    ApiConnectorPackListResponse,
    ApiConnectorPackSummary,
)
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers.integration_pack_schemas import (
    InstallApiConnectorPackRequest,
    InstallApiConnectorPackResponse,
)

router = APIRouter(prefix="/integration-packs", tags=["integration-packs"])


def _actor(user: UserDTO) -> ActorContext:
    return ActorContext(tenant_id=user.tenant_id, user_id=user.id, user_role=user.role)


@router.get("", response_model=ApiConnectorPackListResponse)
async def list_api_connector_packs(
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.API_CONNECTORS_READ)),
):
    del db, current_user
    catalog = ApiConnectorPackCatalog()
    return ApiConnectorPackListResponse(
        items=[
            ApiConnectorPackSummary(
                pack_id=manifest.pack_id,
                version=manifest.version,
                name=manifest.connector.name,
                description=manifest.connector.description,
            )
            for manifest in catalog.list()
        ]
    )


@router.post(
    "/install",
    response_model=InstallApiConnectorPackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def install_api_connector_pack(
    body: InstallApiConnectorPackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.API_CONNECTORS_CREATE)),
):
    catalog = ApiConnectorPackCatalog()
    try:
        manifest = catalog.get(body.pack_id)
    except ResourceNotFoundError as exc:
        raise ResourceNotFoundError(str(exc)) from exc
    service = ApiConnectorService(tenant_id=current_user.tenant_id, db_session=db)
    connector, summary = await service.install_integration_pack_for_actor(
        actor=_actor(current_user),
        manifest=manifest,
        oauth=InstallPackOAuthInput(
            client_id=body.client_id,
            client_secret=body.client_secret,
            redirect_uri=body.redirect_uri,
        ),
    )
    return InstallApiConnectorPackResponse(connector=connector, sync_summary=summary)