"""Document sync routes — Google Drive OAuth, connections, and connectors."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_file_storage, get_settings
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.exceptions import AuthenticationError, ResourceNotFoundError, ValidationError
from apps.shared.core.transaction import transaction
from apps.shared.db.session import get_db
from apps.shared.document.sync_schemas import (
    CreateSyncConnectorRequest,
    DocumentSourceConnectionResponse,
    DriveAuthorizeResponse,
    DrivePickerConfigResponse,
    SyncConnectorResponse,
    SyncConnectorResultResponse,
)
from apps.shared.document.sync_service import DocumentSyncService
from apps.shared.domain.actor import ActorContext
from apps.shared.infra.storage import FileStorage
from apps.shared.schemas.user import UserDTO

router = APIRouter(tags=["document-sync"])


def _create_service(db: AsyncSession, tenant_id: int, file_storage: FileStorage) -> DocumentSyncService:
    return DocumentSyncService(tenant_id=tenant_id, db_session=db, file_storage=file_storage)


def get_file_storage_dependency() -> FileStorage:
    return get_file_storage()


def _actor_from_user(current_user: UserDTO) -> ActorContext:
    return ActorContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


@router.get("/document-sync/google/authorize", response_model=DriveAuthorizeResponse)
@transaction
async def google_drive_authorize(
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    service = _create_service(db, current_user.tenant_id, file_storage)
    return await service.start_google_authorize(user_id=current_user.id)


@router.get("/document-sync/google/callback")
async def google_drive_callback(
    state: str,
    code: str,
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    settings = get_settings()
    portal = settings.PORTAL_ORIGIN.rstrip("/")
    try:
        await DocumentSyncService.handle_google_callback_unscoped(
            db,
            file_storage,
            state=state,
            code=code,
        )
        await db.commit()
        return RedirectResponse(f"{portal}/knowledge-base?drive=connected")
    except (AuthenticationError, ResourceNotFoundError, ValidationError):
        await db.rollback()
        return RedirectResponse(f"{portal}/knowledge-base?drive=error")


@router.get("/document-sync/connections", response_model=list[DocumentSourceConnectionResponse])
async def list_drive_connections(
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    service = _create_service(db, current_user.tenant_id, file_storage)
    return await service.list_connections(owner_id=current_user.id)


@router.get(
    "/document-sync/connections/{connection_id}/picker-config",
    response_model=DrivePickerConfigResponse,
)
async def get_drive_picker_config(
    connection_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    service = _create_service(db, current_user.tenant_id, file_storage)
    return await service.get_picker_config(connection_id=connection_id, owner_id=current_user.id)


@router.delete("/document-sync/connections/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
@transaction
async def disconnect_drive_connection(
    connection_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    service = _create_service(db, current_user.tenant_id, file_storage)
    await service.disconnect_connection(connection_id=connection_id, owner_id=current_user.id)


@router.post(
    "/document-collections/{collection_id}/sync-connector",
    response_model=SyncConnectorResponse,
    status_code=status.HTTP_201_CREATED,
)
@transaction
async def create_sync_connector(
    collection_id: int,
    payload: CreateSyncConnectorRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_WRITE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    service = _create_service(db, current_user.tenant_id, file_storage)
    return await service.create_connector(
        collection_id=collection_id,
        request=payload,
        actor=_actor_from_user(current_user),
    )


@router.get("/document-collections/{collection_id}/sync-connector", response_model=SyncConnectorResponse | None)
async def get_sync_connector(
    collection_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_READ)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    service = _create_service(db, current_user.tenant_id, file_storage)
    return await service.get_connector(collection_id=collection_id, actor=_actor_from_user(current_user))


@router.delete("/document-collections/{collection_id}/sync-connector", status_code=status.HTTP_204_NO_CONTENT)
@transaction
async def delete_sync_connector(
    collection_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_READ)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    service = _create_service(db, current_user.tenant_id, file_storage)
    await service.delete_connector(collection_id=collection_id, actor=_actor_from_user(current_user))


@router.post("/document-sync/connectors/{connector_id}/sync", response_model=SyncConnectorResultResponse)
@transaction
async def trigger_connector_sync(
    connector_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_READ)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    service = _create_service(db, current_user.tenant_id, file_storage)
    return await service.sync_connector(connector_id=connector_id, actor=_actor_from_user(current_user))
