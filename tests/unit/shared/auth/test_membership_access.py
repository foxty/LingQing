"""Unit tests for shared membership access rules."""

import pytest

from apps.shared.auth.membership_access import (
    LOGIN_BLOCKED_ACCOUNT_DISABLED,
    LOGIN_BLOCKED_MEMBERSHIP_INACTIVE,
    MembershipStatus,
    UserAccountStatus,
    login_blocked_reason,
)


@pytest.mark.parametrize(
    "membership_status,account_status,expected",
    [
        (MembershipStatus.ACTIVE, UserAccountStatus.ACTIVE, None),
        (MembershipStatus.INACTIVE, UserAccountStatus.ACTIVE, LOGIN_BLOCKED_MEMBERSHIP_INACTIVE),
        (MembershipStatus.ACTIVE, UserAccountStatus.INACTIVE, LOGIN_BLOCKED_ACCOUNT_DISABLED),
        (MembershipStatus.INACTIVE, UserAccountStatus.INACTIVE, LOGIN_BLOCKED_MEMBERSHIP_INACTIVE),
    ],
)
def test_login_blocked_reason(membership_status, account_status, expected):
    assert login_blocked_reason(membership_status=membership_status, account_status=account_status) == expected
