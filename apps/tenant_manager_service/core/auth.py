"""Authentication and authorization dependencies for tenant manager."""

from collections.abc import Iterable

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.authz.tm_rbac import role_has_tm_permission
from apps.shared.core.exceptions import AuthenticationError, AuthorizationError
from apps.tenant_manager_service.db.session import get_tenant_manager_db
from apps.tenant_manager_service.repositories.user_repository import TenantManagerUserRepository
from apps.tenant_manager_service.schemas import TMPrincipal

security = HTTPBearer()


def decode_tm_token(token: str) -> TMPrincipal:
    """Decode and validate tenant manager JWT token."""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        scope = payload.get("scope")
        if scope != "tenant-manager":
            raise AuthenticationError("Invalid token scope")

        user_id = payload.get("user_id")
        username = payload.get("sub")
        role = payload.get("role")
        provider = payload.get("provider", "native")
        if user_id is None or username is None or role is None:
            raise AuthenticationError("Invalid token payload")

        return TMPrincipal(sub=username, user_id=user_id, role=role, provider=provider)
    except JWTError as e:
        raise AuthenticationError("Could not validate credentials") from e


def get_current_tm_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TMPrincipal:
    """Extract and validate tenant manager principal from bearer token."""
    return decode_tm_token(credentials.credentials)


async def _require_active_tm_user(current_user: TMPrincipal, db: AsyncSession) -> TMPrincipal:
    """Ensure JWT principal maps to an active local TM user.

    This prevents disabled or role-changed users from continuing to use stale tokens.
    """
    repository = TenantManagerUserRepository(db)
    db_user = await repository.get_by_id(current_user.user_id)
    if not db_user:
        raise AuthenticationError("User not found")
    if db_user.status != "active":
        raise AuthorizationError("User is inactive")
    if db_user.role != current_user.role:
        raise AuthorizationError("Token role mismatch")
    return current_user


def require_tm_permission(permission: str | Iterable[str]):
    """Dependency factory requiring at least one TM permission."""
    required_permissions = [permission] if isinstance(permission, str) else list(permission)
    if not required_permissions:
        raise ValueError("require_tm_permission() requires at least one permission")

    async def permission_checker(
        current_user: TMPrincipal = Depends(get_current_tm_user),
        db: AsyncSession = Depends(get_tenant_manager_db),
    ) -> TMPrincipal:
        await _require_active_tm_user(current_user=current_user, db=db)
        for required in required_permissions:
            if role_has_tm_permission(current_user.role, required):
                return current_user
        raise AuthorizationError("Insufficient permissions")

    return permission_checker
