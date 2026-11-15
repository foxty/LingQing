"""Unit tests for secret merge contract."""

from apps.shared.utils.secret_wire import API_SECRET_PLACEHOLDER, mask_secret_for_display
from apps.shared.utils.secret_merge import (
    is_preserve_secret_value,
    merge_dict_preserve_secrets,
    merge_secret_value,
)


def test_preserve_only_empty_and_missing():
    assert is_preserve_secret_value(None) is True
    assert is_preserve_secret_value("") is True
    assert is_preserve_secret_value("   ") is True
    assert is_preserve_secret_value(API_SECRET_PLACEHOLDER) is False
    assert is_preserve_secret_value("********") is False
    assert is_preserve_secret_value(mask_secret_for_display("secretkey")) is False
    assert is_preserve_secret_value("new-secret") is False


def test_merge_secret_value_keeps_existing_on_empty():
    assert merge_secret_value("stored", None) == "stored"
    assert merge_secret_value("stored", "") == "stored"
    assert merge_secret_value("stored", "replacement") == "replacement"


def test_merge_secret_value_does_not_treat_placeholder_as_preserve():
    assert merge_secret_value("stored", API_SECRET_PLACEHOLDER) == API_SECRET_PLACEHOLDER


def test_merge_dict_preserve_secrets_root_password_omitted():
    existing = {"host": "h", "password": "stored-pw"}
    incoming = {"host": "h2"}
    merged = merge_dict_preserve_secrets(existing, incoming, sensitive_keys={"password"})
    assert merged["host"] == "h2"
    assert merged["password"] == "stored-pw"


def test_merge_dict_preserve_secrets_root_password_empty():
    existing = {"host": "h", "password": "stored-pw"}
    incoming = {"host": "h2", "password": ""}
    merged = merge_dict_preserve_secrets(existing, incoming, sensitive_keys={"password"})
    assert merged["host"] == "h2"
    assert merged["password"] == "stored-pw"


def test_merge_dict_nested_metadata_sync():
    existing = {"metadata_sync": {"username": "u", "password": "sync-pw"}}
    incoming = {"metadata_sync": {"username": "u2"}}
    merged = merge_dict_preserve_secrets(existing, incoming, sensitive_keys={"password"})
    assert merged["metadata_sync"]["username"] == "u2"
    assert merged["metadata_sync"]["password"] == "sync-pw"