"""Shared tenant membership and account access rules."""

from __future__ import annotations

from apps.shared.domain.membership import MembershipStatus, UserAccountStatus

LOGIN_BLOCKED_MEMBERSHIP_INACTIVE = "membership_inactive"
LOGIN_BLOCKED_ACCOUNT_DISABLED = "account_disabled"


def login_blocked_reason(*, membership_status: str, account_status: str) -> str | None:
    """Return a denial reason when login/API access should be blocked, else None."""
    if membership_status != MembershipStatus.ACTIVE:
        return LOGIN_BLOCKED_MEMBERSHIP_INACTIVE
    if account_status != UserAccountStatus.ACTIVE:
        return LOGIN_BLOCKED_ACCOUNT_DISABLED
    return None


__all__ = [
    "LOGIN_BLOCKED_ACCOUNT_DISABLED",
    "LOGIN_BLOCKED_MEMBERSHIP_INACTIVE",
    "MembershipStatus",
    "UserAccountStatus",
    "login_blocked_reason",
]