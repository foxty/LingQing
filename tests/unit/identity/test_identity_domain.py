"""Unit tests for identity admin domain rules."""

import pytest

from apps.tenant_app_service.identity.domain import can_enable_force_sso, validate_policy


@pytest.mark.parametrize(
    "count,expected",
    [
        (0, False),
        (1, True),
        (2, True),
    ],
)
def test_can_enable_force_sso(count, expected):
    assert can_enable_force_sso(count) is expected


def test_validate_policy_rejects_unknown():
    with pytest.raises(Exception):
        validate_policy("bogus")
