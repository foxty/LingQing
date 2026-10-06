"""Tests for message feedback domain helpers."""

from apps.tenant_app_service.message_feedback.domain import truncate_preview


def test_truncate_preview_returns_none_for_empty():
    assert truncate_preview(None) is None
    assert truncate_preview("   ") is None


def test_truncate_preview_truncates_long_text():
    text = "a" * 210
    result = truncate_preview(text, max_len=200)
    assert result is not None
    assert len(result) == 200
    assert result.endswith("...")
