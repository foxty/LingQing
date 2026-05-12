from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from jose import jwt

from apps.shared.authz.tm_permissions import TenantManagerPermissions as Permissions
from apps.shared.core.exceptions import AuthenticationError, AuthorizationError
from apps.tenant_manager_service.core.auth import _require_active_tm_user, decode_tm_token, require_tm_permission
from apps.tenant_manager_service.schemas import TMPrincipal

TEST_SECRET_KEY = "test-secret-key"
TEST_ALGORITHM = "HS256"


def _create_tm_token(
    *, user_id: int = 1, username: str = "tm_admin", role: str = "platform_admin", scope: str = "tenant-manager"
) -> str:
    payload = {
        "sub": username,
        "user_id": user_id,
        "role": role,
        "provider": "native",
        "scope": scope,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, TEST_SECRET_KEY, algorithm=TEST_ALGORITHM)


def test_decode_tm_token_success():
    token = _create_tm_token(role="platform_ops")

    principal = decode_tm_token(token)

    assert isinstance(principal, TMPrincipal)
    assert principal.sub == "tm_admin"
    assert principal.user_id == 1
    assert principal.role == "platform_ops"
    assert principal.provider == "native"


def test_decode_tm_token_rejects_non_tm_scope():
    token = _create_tm_token(scope="tenant-app")

    with pytest.raises(AuthenticationError, match="Invalid token scope"):
        decode_tm_token(token)


def test_decode_tm_token_rejects_missing_required_fields():
    payload = {
        "sub": "tm_admin",
        "user_id": 1,
        "scope": "tenant-manager",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    token = jwt.encode(payload, TEST_SECRET_KEY, algorithm=TEST_ALGORITHM)

    with pytest.raises(AuthenticationError, match="Invalid token payload"):
        decode_tm_token(token)


@pytest.mark.asyncio
async def test_require_tm_permission_allows_authorized_role(monkeypatch):
    permission_checker = require_tm_permission(Permissions.LIFECYCLE_LOCK)
    principal = TMPrincipal(sub="ops", user_id=2, role="platform_ops", provider="native")

    async def _allow_active_user(*, current_user: TMPrincipal, db):
        return current_user

    monkeypatch.setattr("apps.tenant_manager_service.core.auth._require_active_tm_user", _allow_active_user)

    authorized = await permission_checker(current_user=principal, db=object())

    assert authorized == principal


@pytest.mark.asyncio
async def test_require_tm_permission_denies_unauthorized_role(monkeypatch):
    permission_checker = require_tm_permission(Permissions.TENANTS_CREATE)
    principal = TMPrincipal(sub="viewer", user_id=3, role="viewer", provider="native")

    async def _allow_active_user(*, current_user: TMPrincipal, db):
        return current_user

    monkeypatch.setattr("apps.tenant_manager_service.core.auth._require_active_tm_user", _allow_active_user)

    with pytest.raises(AuthorizationError, match="Insufficient permissions"):
        await permission_checker(current_user=principal, db=object())


def test_require_tm_permission_requires_at_least_one_permission():
    with pytest.raises(ValueError, match="requires at least one permission"):
        require_tm_permission([])


@pytest.mark.asyncio
async def test_require_active_tm_user_rejects_missing_user(monkeypatch):
    principal = TMPrincipal(sub="ops", user_id=999, role="platform_ops", provider="native")

    mock_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=None))
    monkeypatch.setattr(
        "apps.tenant_manager_service.core.auth.TenantManagerUserRepository",
        lambda db: mock_repo,
    )

    with pytest.raises(AuthenticationError, match="User not found"):
        await _require_active_tm_user(current_user=principal, db=object())


@pytest.mark.asyncio
async def test_require_active_tm_user_rejects_inactive_user(monkeypatch):
    principal = TMPrincipal(sub="ops", user_id=2, role="platform_ops", provider="native")
    db_user = SimpleNamespace(id=2, role="platform_ops", status="inactive")

    mock_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=db_user))
    monkeypatch.setattr(
        "apps.tenant_manager_service.core.auth.TenantManagerUserRepository",
        lambda db: mock_repo,
    )

    with pytest.raises(AuthorizationError, match="User is inactive"):
        await _require_active_tm_user(current_user=principal, db=object())


@pytest.mark.asyncio
async def test_require_active_tm_user_rejects_role_mismatch(monkeypatch):
    principal = TMPrincipal(sub="ops", user_id=2, role="platform_admin", provider="native")
    db_user = SimpleNamespace(id=2, role="platform_ops", status="active")

    mock_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=db_user))
    monkeypatch.setattr(
        "apps.tenant_manager_service.core.auth.TenantManagerUserRepository",
        lambda db: mock_repo,
    )

    with pytest.raises(AuthorizationError, match="Token role mismatch"):
        await _require_active_tm_user(current_user=principal, db=object())
