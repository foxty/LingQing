"""Authentication utilities and dependencies."""

import re
from collections.abc import Iterable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.auth.membership_access import login_blocked_reason
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import TenantMembership, User
from apps.shared.db.session import app_db_session, get_db
from apps.shared.schemas.tenant import LLMDefaultsDTO, TenantConfigDTO, TenantDTO
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

# HTTP Bearer token security scheme (optional to allow cookie fallback)
security = HTTPBearer(auto_error=False)

AUTH_COOKIE_NAME = "access_token"
# Allow cookie auth fallback for read-only render routes and static asset files.
_COOKIE_AUTH_RENDER_PATH = re.compile(
    r"^(/api)?/apps/\d+/[A-Za-z0-9_-]+/(entry|embed|.+\.[A-Za-z0-9]+)$"
)
# Allow cookie auth for v1 data API routes used by the embedded SDK.
_COOKIE_AUTH_DATA_PATH = re.compile(
    r"^(/api)?/apps/v1/\d+/[A-Za-z0-9_-]+/data/(query|mutate|import)$"
)


def _allow_cookie_auth(request: Request) -> bool:
    """Allow cookie fallback on live-app render pages and embedded SDK data routes."""
    path = request.url.path
    method = request.method.upper()
    if method == "GET" and _COOKIE_AUTH_RENDER_PATH.match(path):
        return True
    if method == "POST" and _COOKIE_AUTH_DATA_PATH.match(path):
        return True
    return False


async def _resolve_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> UserDTO:
    """Load and validate the current user using an already-open session."""
    settings = get_settings()
    token: str | None = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif _allow_cookie_auth(request):
        raw_cookie = request.cookies.get(AUTH_COOKIE_NAME)
        if raw_cookie:
            token = raw_cookie.strip()
            if token.lower().startswith("bearer "):
                token = token[7:].strip()

    unauthenticated_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise unauthenticated_exception

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("user_id")
        username = payload.get("sub")
        role = payload.get("role")
        tenant_id = payload.get("tenant_id")
        tenant_name = payload.get("tenant_name")

        if (
            not isinstance(user_id, int)
            or not isinstance(username, str)
            or not username.strip()
            or not isinstance(role, str)
            or not role.strip()
            or not isinstance(tenant_id, int)
            or not isinstance(tenant_name, str)
            or not tenant_name.strip()
        ):
            logger.warning("Token missing or invalid required fields")
            raise credentials_exception

        user_repo = BaseRepository(User, db)
        db_user = await user_repo.get_by_id(user_id)
        if not db_user or db_user.tenant_id != tenant_id:
            logger.warning("Token user not found or tenant mismatch: user_id=%s tenant_id=%s", user_id, tenant_id)
            raise credentials_exception

        membership_result = await db.execute(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.user_id == user_id,
            )
        )
        membership = membership_result.scalar_one_or_none()
        if not membership:
            logger.warning("Token membership not found: user_id=%s tenant_id=%s", user_id, tenant_id)
            raise credentials_exception

        blocked = login_blocked_reason(
            membership_status=membership.status,
            account_status=db_user.status,
        )
        if blocked:
            logger.warning(
                "Token user access blocked: user_id=%s tenant_id=%s reason=%s",
                user_id,
                tenant_id,
                blocked,
            )
            raise credentials_exception

        timezone_pref: str | None = None
        if isinstance(db_user.preferences, dict):
            maybe_timezone = db_user.preferences.get("timezone_iana")
            if isinstance(maybe_timezone, str):
                timezone_pref = maybe_timezone

        return UserDTO(
            id=user_id,
            username=username,
            role=role,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            timezone_iana=timezone_pref,
        )

    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise credentials_exception


async def _ensure_permission(db: AsyncSession, current_user: UserDTO, required_permissions: list[str]) -> UserDTO:
    for required in required_permissions:
        has_permission = await role_has_permission(
            db=db,
            tenant_id=current_user.tenant_id,
            role_key=current_user.role,
            permission=required,
        )
        if has_permission:
            return current_user

    logger.warning(
        f"User {current_user.username} (tenant={current_user.tenant_id}, role={current_user.role}) "
        "attempted to access endpoint requiring permissions: "
        f"{required_permissions}"
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions.",
    )


def _required_permissions(permission: str | Iterable[str]) -> list[str]:
    required_permissions = [permission] if isinstance(permission, str) else list(permission)
    if not required_permissions:
        raise ValueError("require_permission() requires at least one permission")
    return required_permissions


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> UserDTO:
    """Extract and verify current user from JWT token.

    Uses Depends(get_db). FastAPI keeps that yielded session open until the
    response is sent. Fine for short CRUD routes that already hold a request
    session. Long-running routes must use require_permission_released() instead.

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        User object with username, role, tenant_id, and tenant_name

    Raises:
        HTTPException: If token is invalid or expired
    """
    return await _resolve_current_user(request, credentials, db)


def require_role(allowed_roles: list[str]):
    """Dependency factory to check if user has required role.

    Args:
        allowed_roles: List of roles that are allowed

    Returns:
        Dependency function that validates user role
    """

    def role_checker(current_user: UserDTO = Depends(get_current_user)) -> UserDTO:
        """Check if current user has required role.

        Args:
            current_user: Current authenticated user

        Returns:
            User object if authorized

        Raises:
            HTTPException: If user doesn't have required role
        """
        if current_user.role not in allowed_roles:
            logger.warning(
                f"User {current_user.username} with role {current_user.role} "
                f"attempted to access endpoint requiring roles: {allowed_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {allowed_roles}",
            )
        return current_user

    return role_checker


def require_permission(permission: str | Iterable[str]):
    """Dependency factory to check if user has at least one required permission.

    Uses Depends(get_db) via get_current_user. FastAPI keeps that session open
    until the response is sent. Use require_permission_released() on routes that
    wait on warehouse or other external I/O after auth.
    """
    required_permissions = _required_permissions(permission)

    async def permission_checker(
        current_user: UserDTO = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> UserDTO:
        return await _ensure_permission(db, current_user, required_permissions)

    return permission_checker


def require_permission_released(permission: str | Iterable[str]):
    """Authorize without Depends(get_db).

    Do not use Depends(get_db) here. FastAPI does not resume a yielded
    get_db dependency until the response is sent, so the pool connection
    would stay checked out across any later warehouse or network wait.
    This dependency opens a short app_db_session, resolves user + permission,
    and closes the session before the route handler runs.
    """
    required_permissions = _required_permissions(permission)

    async def permission_checker(
        request: Request,
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ) -> UserDTO:
        async with app_db_session() as db:
            current_user = await _resolve_current_user(request, credentials, db)
            return await _ensure_permission(db, current_user, required_permissions)

    return permission_checker


def require_tenant_admin():
    """New admin-only dependency based on permissions."""
    return require_permission(Permissions.TENANT_ADMIN)


async def get_current_tenant(
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantDTO:
    """Get the current tenant DTO.

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        TenantDTO for the current tenant context
    """
    from apps.shared.db.base_repository import BaseRepository
    from apps.shared.db.models import Tenant

    tenant_repo = BaseRepository(Tenant, db)
    tenant = await tenant_repo.get_by_id(current_user.tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {current_user.tenant_id} not found",
        )

    config = None
    if tenant.config and tenant.config.get("llm_defaults"):
        config = TenantConfigDTO(llm_defaults=LLMDefaultsDTO(**tenant.config["llm_defaults"]))

    return TenantDTO(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        description=tenant.description or "",
        config=config,
    )
