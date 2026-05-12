"""Auth router for tenant manager local users."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.tm_permissions import TenantManagerPermissions as Permissions
from apps.shared.core.exceptions import AuthorizationError
from apps.tenant_manager_service.core.auth import get_current_tm_user, require_tm_permission
from apps.tenant_manager_service.db.session import get_tenant_manager_db
from apps.tenant_manager_service.repositories.user_repository import TenantManagerUserRepository
from apps.tenant_manager_service.schemas import TMBootstrapAdminRequest, TMLoginRequest, TMLoginResponse, TMUserResponse
from apps.tenant_manager_service.services.tm_local_user_service import TMLocalUserService

router = APIRouter(prefix="/auth", tags=["auth"])


def _build_service(db: AsyncSession) -> TMLocalUserService:
    return TMLocalUserService(TenantManagerUserRepository(db))


@router.post("/login", response_model=TMLoginResponse)
async def login(payload: TMLoginRequest, db: AsyncSession = Depends(get_tenant_manager_db)):
    """Native login for tenant manager."""
    service = _build_service(db)
    token, user = await service.login(payload.username, payload.password)
    return TMLoginResponse(access_token=token, token_type="bearer", user=TMUserResponse.model_validate(user))


@router.post("/bootstrap-admin", response_model=TMUserResponse)
async def bootstrap_admin(payload: TMBootstrapAdminRequest, db: AsyncSession = Depends(get_tenant_manager_db)):
    """Initialize the first platform admin for tenant manager."""
    service = _build_service(db)
    user = await service.bootstrap_admin(
        username=payload.username,
        display_name=payload.display_name,
        password=payload.password,
    )
    return TMUserResponse.model_validate(user)


@router.get("/me", response_model=TMUserResponse)
async def me(
    principal=Depends(get_current_tm_user),
    db: AsyncSession = Depends(get_tenant_manager_db),
):
    """Get current tenant manager user profile."""
    service = _build_service(db)
    matched = await service.get_user(principal.user_id)
    if matched.status != "active":
        raise AuthorizationError("User is inactive")
    return TMUserResponse.model_validate(matched)


@router.get("/permissions/check")
async def check_permission(
    principal=Depends(require_tm_permission(Permissions.TENANTS_READ)),
):
    """Simple endpoint to verify tenant-manager permission guard."""
    return {"user": principal.sub, "role": principal.role, "allowed": True}
