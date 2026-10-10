"""Authentication router (native login, profile, and public SSO login flow)."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.authz.ta_rbac import get_effective_rbac
from apps.shared.core.auth import get_current_user, set_access_token_cookie
from apps.shared.core.rate_limit import rate_limiter
from apps.shared.db.session import get_db
from apps.shared.domain.types import RESOURCE_TYPE_USER
from apps.shared.schemas.user import UserDTO
from apps.shared.tag.adapters import domain_tag_value_to_api
from apps.shared.tag.schemas import TagValueDTO
from apps.shared.tag.service import TagService
from apps.tenant_app_service.auth.adapters import (
    domain_user_to_profile_response,
)
from apps.tenant_app_service.auth.schemas import (
    ChangePasswordRequest,
    InviteAcceptRequest,
    InviteAcceptResponse,
    LoginRequest,
    LoginResponse,
    ProfileResponse,
    ResetPasswordRequest,
    UpdateProfilePreferencesRequest,
)
from apps.tenant_app_service.auth.service import AuthService
from apps.tenant_app_service.sso.dtos import (
    ResolveTenantMethodsRequest,
    ResolveTenantMethodsResponse,
    SsoExchangeRequest,
    SsoExchangeResponse,
    SsoStartResponse,
)
from apps.tenant_app_service.sso.login_service import SsoLoginService
from apps.tenant_app_service.sso.services import SsoAdminService

router = APIRouter(prefix="/auth", tags=["authentication"], include_in_schema=False)

_PUBLIC_AUTH_MAX_EVENTS = 20
_PUBLIC_AUTH_WINDOW_SECONDS = 900
_TOO_MANY_REQUESTS = "Too many requests. Please try again later."
_TOO_MANY_LOGIN = "Too many login attempts. Please try again later."


def _public_auth_limit(name: str, *, detail: str = _TOO_MANY_REQUESTS):
    return Depends(rate_limiter(name, _PUBLIC_AUTH_MAX_EVENTS, _PUBLIC_AUTH_WINDOW_SECONDS, detail=detail))


@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[_public_auth_limit("auth.login", detail=_TOO_MANY_LOGIN)],
)
async def login(
    credentials: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user and return JWT token.

    Args:
        credentials: Login credentials (API schema)
        db: Database session

    Returns:
        LoginResponse with access token and user info
    """
    auth_service = AuthService(db=db)
    login_response = await auth_service.authenticate(credentials)
    set_access_token_cookie(response, login_response.access_token)
    return login_response


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's profile.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        ProfileResponse with complete user information and effective permissions
    """
    auth_service = AuthService(db=db)
    domain_user = await auth_service.get_user_profile(current_user.id)

    # Load effective RBAC for this user's role and tenant
    effective_rbac = await get_effective_rbac(db, current_user.tenant_id)
    role_perms = effective_rbac.roles.get(current_user.role, set())
    permissions = sorted(list(role_perms))

    return await domain_user_to_profile_response(domain_user, current_user.tenant_name, permissions)


@router.patch("/profile/preferences", response_model=ProfileResponse)
async def update_profile_preferences(
    request: UpdateProfilePreferencesRequest,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update current user's profile preferences."""
    auth_service = AuthService(db=db)
    domain_user = await auth_service.update_profile_preferences(current_user.id, timezone_iana=request.timezone_iana)

    effective_rbac = await get_effective_rbac(db, current_user.tenant_id)
    role_perms = effective_rbac.roles.get(current_user.role, set())
    permissions = sorted(list(role_perms))

    return await domain_user_to_profile_response(domain_user, current_user.tenant_name, permissions)


@router.get("/profile/tags", response_model=list[TagValueDTO])
async def get_profile_tags(
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's tags.

    Requires tag read/manage permissions and only returns tags for current user.
    """
    tag_service = TagService.create(current_user.tenant_id, db)
    tag_values = await tag_service.list_tags_for_resource(RESOURCE_TYPE_USER, current_user.id)
    return [domain_tag_value_to_api(tag_value) for tag_value in tag_values]


@router.post("/profile/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    request: ChangePasswordRequest,
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change current user's password.

    Args:
        request: Password change request
        current_user: Current authenticated user
        db: Database session

    Raises:
        HTTPException: If validation fails or old password is incorrect
    """
    # Validate passwords match
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password and confirmation do not match",
        )

    # Convert to domain and call service
    auth_service = AuthService(db=db)

    await auth_service.change_password(
        user_id=current_user.id,
        old_password=request.old_password,
        new_password=request.new_password,
    )


@router.post(
    "/invite/accept",
    response_model=InviteAcceptResponse,
    dependencies=[_public_auth_limit("auth.invite.accept")],
)
async def accept_invite(request: InviteAcceptRequest, db: AsyncSession = Depends(get_db)):
    """Accept invite and set password (Phase 0 stub)."""
    auth_service = AuthService(db=db)
    return await auth_service.accept_invite(request.token, request.password)


@router.post(
    "/password/reset",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_public_auth_limit("auth.password.reset")],
)
async def reset_password(request: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Reset password with token (Phase 0 stub)."""
    auth_service = AuthService(db=db)
    await auth_service.reset_password_with_token(request.token, request.new_password)


# ============ Public SSO login (unauthenticated) ============


@router.post(
    "/resolve-tenant-methods",
    response_model=ResolveTenantMethodsResponse,
    dependencies=[_public_auth_limit("auth.resolve_tenant_methods")],
)
async def resolve_tenant_methods(request: ResolveTenantMethodsRequest, db: AsyncSession = Depends(get_db)):
    service = SsoAdminService(db)
    return await service.resolve_tenant_methods(request.identifier)


@router.get(
    "/sso/{provider_id}/start",
    response_model=SsoStartResponse,
    dependencies=[_public_auth_limit("auth.sso.start")],
)
async def sso_start(
    provider_id: int,
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
):
    service = SsoLoginService(db)
    return await service.start(tenant_id=tenant_id, provider_id=provider_id)


@router.get("/sso/callback", dependencies=[_public_auth_limit("auth.sso.callback")])
async def sso_callback(
    state: str,
    code: str,
    provider_id: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = SsoLoginService(db)
    result = await service.handle_callback(state=state, code=code, provider_id=provider_id)

    settings = get_settings()
    portal = settings.PORTAL_ORIGIN.rstrip("/")
    if result.status == "success" and result.ticket:
        return RedirectResponse(f"{portal}/login/sso?ticket={result.ticket}")
    if result.status == "pending":
        return RedirectResponse(f"{portal}/login/sso?status=pending")

    reason = quote(result.reason or "unknown", safe="")
    return RedirectResponse(f"{portal}/login/sso?status=denied&reason={reason}")


@router.post(
    "/sso/exchange",
    response_model=SsoExchangeResponse,
    dependencies=[_public_auth_limit("auth.sso.exchange")],
)
async def sso_exchange(
    request: SsoExchangeRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    service = SsoLoginService(db)
    result = await service.exchange_ticket(request.ticket)
    set_access_token_cookie(response, result.access_token)
    return result
