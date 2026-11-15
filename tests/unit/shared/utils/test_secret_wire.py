"""Contract tests for secret wire (sync with portal ``secretWire.test.ts``)."""

import pytest

from apps.shared.utils.secret_wire import (
    API_SECRET_PLACEHOLDER,
    is_display_mask,
    is_unchanged_secret_on_wire,
    mask_secret_for_display,
)

UNCHANGED_WIRE_VECTORS: list[tuple[object, bool]] = [
    (None, True),
    ("", True),
    ("   ", True),
    (API_SECRET_PLACEHOLDER, False),
    ("********", False),
    (mask_secret_for_display("secretkey"), False),
    ("new-secret", False),
    ("my*pass*word", False),
]


@pytest.mark.parametrize("value,expected", UNCHANGED_WIRE_VECTORS)
def test_is_unchanged_secret_on_wire(value: object, expected: bool) -> None:
    assert is_unchanged_secret_on_wire(value) is expected


def test_mask_secret_for_display_round_trip() -> None:
    plain = "dapiabcdefghij"
    masked = mask_secret_for_display(plain)
    assert masked.startswith("da")
    assert masked.endswith("ij")
    assert is_display_mask(masked)
    assert not is_display_mask(plain)
    assert not is_display_mask(API_SECRET_PLACEHOLDER)


def test_short_values() -> None:
    assert mask_secret_for_display("ab") == "**"
    assert is_display_mask("****")
    assert not is_display_mask("ab")