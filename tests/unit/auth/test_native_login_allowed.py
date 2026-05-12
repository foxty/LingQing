"""Unit tests for auth-domain policy: native_login_allowed.

`native_login_allowed` is the force-SSO gate for password login. It lives in
`auth.domain` (not `sso`) because `force_sso` is a tenant property and the
native auth flow must not depend on the SSO module.
"""

import pytest

from apps.tenant_app_service.auth.domain import native_login_allowed


def test_native_login_allowed_when_force_sso_off():
    assert native_login_allowed(force_sso=False, is_break_glass=False) is True


def test_native_login_blocked_for_non_break_glass_when_force_sso_on():
    assert native_login_allowed(force_sso=True, is_break_glass=False) is False


def test_native_login_allowed_for_break_glass_when_force_sso_on():
    assert native_login_allowed(force_sso=True, is_break_glass=True) is True


@pytest.mark.parametrize(
    "force_sso,break_glass,expected",
    [
        (False, False, True),
        (False, True, True),
        (True, False, False),
        (True, True, True),
    ],
)
def test_native_login_allowed_matrix(force_sso, break_glass, expected):
    assert native_login_allowed(force_sso=force_sso, is_break_glass=break_glass) is expected
