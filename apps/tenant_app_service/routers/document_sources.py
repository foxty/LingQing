"""Document source provider configuration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_file_storage
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.transaction import transaction
from apps.shared.db.session import get_db
from apps.shared.document.sync_schemas import GoogleDriveSourceConfigRequest, GoogleDriveSourceConfigResponse
from apps.shared.document.sync_service import DocumentSyncService
from apps.shared.infra.storage import FileStorage
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/document-sources", tags=["document-sources"])


def _create_service(db: AsyncSession, tenant_id: int, file_storage: FileStorage) -> DocumentSyncService:
    return DocumentSyncService(tenant_id=tenant_id, db_session=db, file_storage=file_storage)


def get_file_storage_dependency() -> FileStorage:
    return get_file_storage()


@router.get("/google-drive", response_model=GoogleDriveSourceConfigResponse)
async def get_google_drive_source(
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    service = _create_service(db, current_user.tenant_id, file_storage)
    return await service.get_google_drive_source()


@router.put("/google-drive", response_model=GoogleDriveSourceConfigResponse)
@transaction
async def upsert_google_drive_source(
    payload: GoogleDriveSourceConfigRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.DOCUMENTS_MANAGE)),
    db: AsyncSession = Depends(get_db),
    file_storage: FileStorage = Depends(get_file_storage_dependency),
):
    service = _create_service(db, current_user.tenant_id, file_storage)
    return await service.upsert_google_drive_source(payload)
