"""Tenant identity admin router."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.identity.dtos import (
    BreakGlassRequest,
    IdentitySettingsResponse,
    IdentitySourceResponse,
    LoginDomainRequest,
    LoginDomainResponse,
    PendingIdentityResponse,
    UpdateIdentitySettingsRequest,
    UpdateIdentitySourceRequest,
)
from apps.tenant_app_service.identity.services import IdentityAdminService

router = APIRouter(tags=["identity"], include_in_schema=False)


@router.get("/tenants/identity-sources", response_model=list[IdentitySourceResponse])
async def list_identity_sources(
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    return await service.list_identity_sources(current_user.tenant_id)


@router.patch(
    "/tenants/identity-sources/{source_id}",
    response_model=IdentitySourceResponse,
)
async def update_identity_source(
    source_id: int,
    request: UpdateIdentitySourceRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    result = await service.update_identity_source(current_user.tenant_id, source_id, request)
    await db.commit()
    return result


@router.get("/tenants/identity/domains", response_model=list[LoginDomainResponse])
async def list_login_domains(
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    return await service.list_domains(current_user.tenant_id)


@router.post(
    "/tenants/identity/domains",
    response_model=list[LoginDomainResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_login_domains(
    request: LoginDomainRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    result = await service.add_domains(current_user.tenant_id, request.domains)
    await db.commit()
    return result


@router.delete("/tenants/identity/domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_login_domain(
    domain_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    await service.remove_domain(current_user.tenant_id, domain_id)
    await db.commit()


@router.get("/tenants/identity/settings", response_model=IdentitySettingsResponse)
async def get_identity_settings(
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    return await service.get_settings(current_user.tenant_id)


@router.put("/tenants/identity/settings", response_model=IdentitySettingsResponse)
async def update_identity_settings(
    request: UpdateIdentitySettingsRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    result = await service.update_force_sso(current_user.tenant_id, request.force_sso)
    await db.commit()
    return result


@router.put("/tenants/users/{user_id}/break-glass", response_model=IdentitySettingsResponse)
async def set_user_break_glass(
    user_id: int,
    request: BreakGlassRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    await service.set_membership_break_glass(current_user.tenant_id, user_id, request.is_break_glass)
    await db.commit()
    return await service.get_settings(current_user.tenant_id)


@router.get("/tenants/identity/pending", response_model=list[PendingIdentityResponse])
async def list_pending_identities(
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    return await service.list_pending(current_user.tenant_id)


@router.post(
    "/tenants/identity/pending/{identity_id}/approve",
    response_model=PendingIdentityResponse,
)
async def approve_pending_identity(
    identity_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    result = await service.approve_pending(current_user.tenant_id, identity_id)
    await db.commit()
    return result


@router.post(
    "/tenants/identity/pending/{identity_id}/reject",
    response_model=PendingIdentityResponse,
)
async def reject_pending_identity(
    identity_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    result = await service.reject_pending(current_user.tenant_id, identity_id)
    await db.commit()
    return result
