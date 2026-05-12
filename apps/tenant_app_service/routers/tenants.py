"""Tenants router."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import get_current_user, require_permission
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.auth.password_validator import validate_password_complexity
from apps.tenant_app_service.tenant import (
    SingleTenantService,
    StatsResponse,
    TenantUserManagementService,
)
from apps.tenant_app_service.tenant.schemas import (
    TenantUserCreateRequest,
    TenantUserDTO,
    TenantUserResetPasswordRequest,
    TenantUserUpdateRequest,
)

router = APIRouter(prefix="/tenants", tags=["tenants"], include_in_schema=False)
logger = get_logger(__name__)


@router.get("/stats", response_model=StatsResponse)
async def get_tenant_stats(
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get statistics for the current user's tenant.

    Both admin and regular users see their own tenant's data.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        StatsResponse with tenant statistics
    """
    service = SingleTenantService.create(db, current_user.tenant_id)
    return await service.get_stats()


# ============ User Management Endpoints ============


@router.get("/users", response_model=list[TenantUserDTO])
async def list_tenant_users(
    current_user: UserDTO = Depends(require_permission(Permissions.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """List tenant users.

    Args:
        current_user: Current authenticated user (permission required)
        db: Database session

    Returns:
        List of users
    """
    service = TenantUserManagementService(tenant_id=current_user.tenant_id, db=db)
    return await service.list_users()


@router.post("/users", response_model=TenantUserDTO)
async def create_tenant_user(
    request: TenantUserCreateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Create tenant user.

    Args:
        request: Create user request
        current_user: Current authenticated user (permission required)
        db: Database session

    Returns:
        Created user
    """
    validate_password_complexity(request.password)
    service = TenantUserManagementService(tenant_id=current_user.tenant_id, db=db)
    return await service.create_user(
        username=request.username,
        password=request.password,
        role=request.role,
        email=request.email,
    )


@router.post("/users/{user_id}/deactivate", status_code=204)
async def deactivate_tenant_user(
    user_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate tenant user.

    Args:
        user_id: User ID
        current_user: Current authenticated user (permission required)
        db: Database session
    """
    service = TenantUserManagementService(tenant_id=current_user.tenant_id, db=db)
    await service.deactivate_user(user_id=user_id, actor_user_id=current_user.id)


@router.post("/users/{user_id}/recover", status_code=204)
async def recover_tenant_user(
    user_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Recover (reactivate) a deactivated tenant user.

    Args:
        user_id: User ID
        current_user: Current authenticated user (permission required)
        db: Database session
    """
    service = TenantUserManagementService(tenant_id=current_user.tenant_id, db=db)
    await service.recover_user(user_id=user_id)


@router.post("/users/{user_id}/reset-password", status_code=204)
async def reset_tenant_user_password(
    user_id: int,
    request: TenantUserResetPasswordRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Reset tenant user password.

    Args:
        user_id: User ID
        request: Reset password request
        current_user: Current authenticated user (permission required)
        db: Database session
    """
    validate_password_complexity(request.new_password)
    service = TenantUserManagementService(tenant_id=current_user.tenant_id, db=db)
    await service.reset_password(user_id=user_id, new_password=request.new_password)


@router.put("/users/{user_id}", response_model=TenantUserDTO)
async def update_tenant_user(
    user_id: int,
    request: TenantUserUpdateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.USERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant user role.

    Args:
        user_id: User ID
        request: Update user request
        current_user: Current authenticated user (permission required)
        db: Database session

    Returns:
        Updated user
    """
    service = TenantUserManagementService(tenant_id=current_user.tenant_id, db=db)
    return await service.update_user_role(
        user_id=user_id,
        role=request.role,
        actor_user_id=current_user.id,
    )


@router.get("/subscription")
async def get_tenant_subscription(
    current_user: UserDTO = Depends(require_permission(Permissions.TENANT_SETTINGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    """Get tenant subscription and billing info (placeholder - coming soon).

    Args:
        current_user: Current authenticated user (permission required)
        db: Database session

    Returns:
        Placeholder response
    """
    return {"message": "Coming soon", "feature": "subscription_billing"}
