import pytest

from apps.shared.domain.types import required_acl_permissions, to_abac_action


def test_manage_maps_to_write_for_abac():
    assert to_abac_action("manage") == "write"


def test_acl_permission_scope_by_action():
    assert required_acl_permissions("read") == ("read", "write", "manage")
    assert required_acl_permissions("write") == ("write", "manage")
    assert required_acl_permissions("manage") == ("manage",)


@pytest.mark.parametrize("value", ["READ", " Write ", "manage"])
def test_action_normalization_is_case_insensitive(value: str):
    _ = required_acl_permissions(value)


@pytest.mark.parametrize("value", ["delete", "", " execute "])
def test_invalid_action_raises(value: str):
    with pytest.raises(ValueError):
        _ = to_abac_action(value)
