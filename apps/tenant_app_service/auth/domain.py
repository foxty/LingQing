"""Domain models for auth module."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from apps.shared.auth.membership_access import (
    LOGIN_BLOCKED_ACCOUNT_DISABLED,
    LOGIN_BLOCKED_MEMBERSHIP_INACTIVE,
    MembershipStatus,
    UserAccountStatus,
    login_blocked_reason,
)
from apps.shared.core.exceptions import ValidationError
from apps.shared.domain.base_domain_model import BaseDomainModel


class UserRole(enum.StrEnum):
    """Tenant-app RBAC role keys."""

    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


# Re-export shared status enums for tenant-app callers.
ROLE_ADMIN = UserRole.ADMIN
MEMBERSHIP_ACTIVE = MembershipStatus.ACTIVE
MEMBERSHIP_INACTIVE = MembershipStatus.INACTIVE
ACCOUNT_ACTIVE = UserAccountStatus.ACTIVE


def assert_tenant_retains_active_admin(*, role: str, other_active_admins: int) -> None:
    """Fail if removing this admin would leave the tenant with none."""
    if role == UserRole.ADMIN and other_active_admins == 0:
        raise ValidationError("Tenant must have at least one admin")


@dataclass
class UserPreferences(BaseDomainModel):
    """Typed user preference payload."""

    timezone_iana: str | None = None

    @classmethod
    def from_raw(cls, raw: object) -> UserPreferences:
        if not isinstance(raw, dict):
            return cls()
        timezone = raw.get("timezone_iana")
        if not isinstance(timezone, str):
            timezone = None
        return cls(timezone_iana=timezone)


@dataclass
class UserDomain(BaseDomainModel):
    """User domain model."""

    id: int
    username: str
    email: str | None
    role: str
    tenant_id: int
    status: str
    preferences: UserPreferences
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def is_active(self) -> bool:
        """Check if user account is active."""
        return self.status == UserAccountStatus.ACTIVE

    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return self.role == UserRole.ADMIN

    def can_access_tenant(self, tenant_id: int) -> bool:
        """Check if user can access given tenant."""
        return self.tenant_id == tenant_id


@dataclass
class PasswordVerifier(Protocol):
    """Protocol for password verification."""

    def verify(self, password: str, hashed: str) -> bool:
        """Verify password against hash."""


@dataclass
class TokenIssuer(Protocol):
    """Port for issuing internal JWTs.

    Both native and SSO login issue the same token shape so downstream auth
    stays unchanged. Implementations live in infra (e.g. JwtTokenIssuer).
    """

    def issue(
        self,
        *,
        user_id: int,
        username: str,
        role: str,
        tenant_id: int,
        tenant_name: str,
    ) -> str:
        """Issue a signed access token for the given identity."""


def native_login_allowed(force_sso: bool, is_break_glass: bool) -> bool:
    """Native password login is allowed when force-SSO is off, or for break-glass.

    `force_sso` is a tenant-level policy flag (column on `tenants`); it is not an
    SSO concept. This keeps the auth module free of any `sso` dependency.
    """
    if not force_sso:
        return True
    return is_break_glass


@dataclass
class UserAuthDomain(BaseDomainModel):
    """User authentication aggregate."""

    user: UserDomain
    membership_status: str
    password_hash: str | None

    def authenticate(self, password: str, verifier: PasswordVerifier) -> UserDomain:
        """Authenticate user within tenant.

        Args:
            password: Plain text password
            verifier: Password verifier implementation

        Returns:
            UserDomain if authentication succeeds
        """
        blocked = login_blocked_reason(
            membership_status=self.membership_status,
            account_status=self.user.status,
        )
        if blocked == LOGIN_BLOCKED_MEMBERSHIP_INACTIVE:
            raise ValidationError("该用户已在当前租户停用", {"code": "AUTH_TENANT_DEACTIVATED"})
        if blocked == LOGIN_BLOCKED_ACCOUNT_DISABLED:
            raise ValidationError("该账号已被禁用", {"code": "AUTH_USER_DISABLED"})

        if not self.password_hash:
            raise ValidationError("用户名或密码错误", {"code": "AUTH_INVALID_CREDENTIALS"})

        if not verifier.verify(password, self.password_hash):
            raise ValidationError("用户名或密码错误", {"code": "AUTH_INVALID_CREDENTIALS"})

        return self.user
