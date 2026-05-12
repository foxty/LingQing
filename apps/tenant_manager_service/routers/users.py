"""User management router for tenant manager local users."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.tm_permissions import TenantManagerPermissions as Permissions
from apps.tenant_manager_service.core.auth import require_tm_permission
from apps.tenant_manager_service.db.session import get_tenant_manager_db
from apps.tenant_manager_service.repositories.user_repository import TenantManagerUserRepository
from apps.tenant_manager_service.schemas import (
    TMUserCreateRequest,
    TMUserListResponse,
    TMUserResponse,
    TMUserUpdateStatusRequest,
)
from apps.tenant_manager_service.services.tm_local_user_service import TMLocalUserService

router = APIRouter(prefix="/users", tags=["users"])


def _build_service(db: AsyncSession) -> TMLocalUserService:
    return TMLocalUserService(TenantManagerUserRepository(db))


@router.get("", response_model=TMUserListResponse)
async def list_users(
    _: object = Depends(require_tm_permission(Permissions.AUDIT_READ)),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """List tenant manager local users."""
    service = _build_service(db)
    users = await service.list_users()
    return TMUserListResponse(items=[TMUserResponse.model_validate(item) for item in users])


@router.post("", response_model=TMUserResponse)
async def create_user(
    payload: TMUserCreateRequest,
    _: object = Depends(require_tm_permission(Permissions.TENANTS_CREATE)),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """Create tenant manager local user."""
    service = _build_service(db)
    user = await service.create_user(
        username=payload.username,
        display_name=payload.display_name,
        password=payload.password,
        role=payload.role,
    )
    return TMUserResponse.model_validate(user)


@router.put("/{user_id}/status", response_model=TMUserResponse)
async def update_user_status(
    user_id: int,
    payload: TMUserUpdateStatusRequest,
    _: object = Depends(require_tm_permission(Permissions.TENANTS_CREATE)),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """Update tenant manager local user status."""
    service = _build_service(db)
    user = await service.update_user_status(user_id=user_id, status=payload.status)
    return TMUserResponse.model_validate(user)
