"""SSO admin and login router.

Provider CRUD and OIDC login flow. Identity admin (domains, settings, pending)
lives in identity/router.py; deprecated aliases below delegate for compatibility.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.identity.dtos import (
    IdentitySettingsResponse,
    IdentitySourceResponse,
    LoginDomainRequest,
    LoginDomainResponse,
    PendingIdentityResponse,
    UpdateIdentitySettingsRequest,
    UpdateIdentitySourceRequest,
)
from apps.tenant_app_service.identity.services import IdentityAdminService
from apps.tenant_app_service.sso.dtos import (
    AuthProviderResponse,
    CreateAuthProviderRequest,
    ResolveTenantMethodsRequest,
    ResolveTenantMethodsResponse,
    SsoExchangeRequest,
    SsoExchangeResponse,
    SsoStartResponse,
    UpdateAuthProviderRequest,
)
from apps.tenant_app_service.sso.login_service import SsoLoginService
from apps.tenant_app_service.sso.services import SsoAdminService

router = APIRouter(tags=["sso"], include_in_schema=False)


# ============ Admin: provider CRUD ============


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


# ============ Deprecated aliases → identity admin ============


@router.get("/tenants/identity-sources", response_model=list[IdentitySourceResponse], deprecated=True)
async def list_identity_sources_deprecated(
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    return await service.list_identity_sources(current_user.tenant_id)


@router.patch(
    "/tenants/identity-sources/{source_id}",
    response_model=IdentitySourceResponse,
    deprecated=True,
)
async def update_identity_source_deprecated(
    source_id: int,
    request: UpdateIdentitySourceRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    result = await service.update_identity_source(current_user.tenant_id, source_id, request)
    await db.commit()
    return result


@router.get("/tenants/sso/domains", response_model=list[LoginDomainResponse], deprecated=True)
async def list_login_domains_deprecated(
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    return await service.list_domains(current_user.tenant_id)


@router.post(
    "/tenants/sso/domains",
    response_model=list[LoginDomainResponse],
    status_code=status.HTTP_201_CREATED,
    deprecated=True,
)
async def add_login_domains_deprecated(
    request: LoginDomainRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    result = await service.add_domains(current_user.tenant_id, request.domains)
    await db.commit()
    return result


@router.delete("/tenants/sso/domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT, deprecated=True)
async def remove_login_domain_deprecated(
    domain_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    await service.remove_domain(current_user.tenant_id, domain_id)
    await db.commit()


@router.get("/tenants/sso/settings", response_model=IdentitySettingsResponse, deprecated=True)
async def get_sso_settings_deprecated(
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    return await service.get_settings(current_user.tenant_id)


@router.put("/tenants/sso/settings", response_model=IdentitySettingsResponse, deprecated=True)
async def update_sso_settings_deprecated(
    request: UpdateIdentitySettingsRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    result = await service.update_force_sso(current_user.tenant_id, request.force_sso)
    await db.commit()
    return result


@router.get("/tenants/sso/pending", response_model=list[PendingIdentityResponse], deprecated=True)
async def list_pending_identities_deprecated(
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    return await service.list_pending(current_user.tenant_id)


@router.post(
    "/tenants/sso/pending/{identity_id}/approve",
    response_model=PendingIdentityResponse,
    deprecated=True,
)
async def approve_pending_identity_deprecated(
    identity_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    result = await service.approve_pending(current_user.tenant_id, identity_id)
    await db.commit()
    return result


@router.post(
    "/tenants/sso/pending/{identity_id}/reject",
    response_model=PendingIdentityResponse,
    deprecated=True,
)
async def reject_pending_identity_deprecated(
    identity_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.AUTH_PROVIDERS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = IdentityAdminService(db)
    result = await service.reject_pending(current_user.tenant_id, identity_id)
    await db.commit()
    return result


# ============ Public: resolve-tenant methods ============


@router.post("/auth/resolve-tenant-methods", response_model=ResolveTenantMethodsResponse)
async def resolve_tenant_methods(request: ResolveTenantMethodsRequest, db: AsyncSession = Depends(get_db)):
    service = SsoAdminService(db)
    return await service.resolve_tenant_methods(request.identifier)


# ============ Public: OIDC start / callback / exchange ============


@router.get("/auth/sso/{provider_id}/start", response_model=SsoStartResponse)
async def sso_start(
    provider_id: int,
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = SsoLoginService(db)
    result = await service.start(tenant_id=tenant_id, provider_id=provider_id)
    await db.commit()
    return result


@router.get("/auth/sso/callback")
async def sso_callback(
    state: str,
    code: str,
    provider_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = SsoLoginService(db)
    result = await service.handle_callback(state=state, code=code, provider_id=provider_id)
    await db.commit()

    settings = get_settings()
    portal = settings.PORTAL_ORIGIN.rstrip("/")
    if result.status == "success" and result.ticket:
        return RedirectResponse(f"{portal}/login/sso?ticket={result.ticket}")
    if result.status == "pending":
        return RedirectResponse(f"{portal}/login/sso?status=pending")
    from urllib.parse import quote

    reason = quote(result.reason or "unknown", safe="")
    return RedirectResponse(f"{portal}/login/sso?status=denied&reason={reason}")


@router.post("/auth/sso/exchange", response_model=SsoExchangeResponse)
async def sso_exchange(
    request: SsoExchangeRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    service = SsoLoginService(db)
    result = await service.exchange_ticket(request.ticket)
    await db.commit()
    response.set_cookie(
        key="access_token",
        value=result.access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/",
    )
    return result
