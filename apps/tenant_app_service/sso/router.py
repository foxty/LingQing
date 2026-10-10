"""SSO provider admin router.

Public login endpoints live in apps.tenant_app_service.routers.auth.
Identity admin lives in identity/router.py.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.sso.dtos import (
    AuthProviderResponse,
    CreateAuthProviderRequest,
    UpdateAuthProviderRequest,
)
from apps.tenant_app_service.sso.services import SsoAdminService

router = APIRouter(tags=["sso"], include_in_schema=False)


@router.get("/tenants/auth-providers", response_model=list[AuthProviderResponse])
async def list_auth_providers(
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = SsoAdminService(db)
    return await service.list_providers(current_user.tenant_id)


@router.post(
    "/tenants/auth-providers",
    response_model=AuthProviderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_auth_provider(
    request: CreateAuthProviderRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = SsoAdminService(db)
    result = await service.create_provider(current_user.tenant_id, request)
    await db.commit()
    return result


@router.get("/tenants/auth-providers/{provider_id}", response_model=AuthProviderResponse)
async def get_auth_provider(
    provider_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = SsoAdminService(db)
    return await service.get_provider(current_user.tenant_id, provider_id)


@router.put("/tenants/auth-providers/{provider_id}", response_model=AuthProviderResponse)
async def update_auth_provider(
    provider_id: int,
    request: UpdateAuthProviderRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = SsoAdminService(db)
    result = await service.update_provider(current_user.tenant_id, provider_id, request)
    await db.commit()
    return result


@router.delete("/tenants/auth-providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_auth_provider(
    provider_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = SsoAdminService(db)
    await service.delete_provider(current_user.tenant_id, provider_id)
    await db.commit()


@router.post(
    "/tenants/auth-providers/{provider_id}/enable",
    response_model=AuthProviderResponse,
)
async def enable_auth_provider(
    provider_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = SsoAdminService(db)
    result = await service.set_provider_enabled(current_user.tenant_id, provider_id, True)
    await db.commit()
    return result


@router.post(
    "/tenants/auth-providers/{provider_id}/disable",
    response_model=AuthProviderResponse,
)
async def disable_auth_provider(
    provider_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = SsoAdminService(db)
    result = await service.set_provider_enabled(current_user.tenant_id, provider_id, False)
    await db.commit()
    return result
