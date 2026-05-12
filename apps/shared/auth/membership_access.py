"""Shared tenant membership and account access rules."""

from __future__ import annotations

import enum

LOGIN_BLOCKED_MEMBERSHIP_INACTIVE = "membership_inactive"
LOGIN_BLOCKED_ACCOUNT_DISABLED = "account_disabled"


class MembershipStatus(enum.StrEnum):
    """Tenant membership lifecycle within one tenant."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class UserAccountStatus(enum.StrEnum):
    """Global user account status."""

    ACTIVE = "active"
    INACTIVE = "inactive"


def login_blocked_reason(*, membership_status: str, account_status: str) -> str | None:
    """Return a denial reason when login/API access should be blocked, else None."""
    if membership_status != MembershipStatus.ACTIVE:
        return LOGIN_BLOCKED_MEMBERSHIP_INACTIVE
    if account_status != UserAccountStatus.ACTIVE:
        return LOGIN_BLOCKED_ACCOUNT_DISABLED
    return None
