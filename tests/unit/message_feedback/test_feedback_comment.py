"""Tests for message feedback comment validation."""

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.message_feedback.domain import (
    FEEDBACK_COMMENT_MAX_LENGTH,
    normalize_feedback_comment,
)


def test_normalize_feedback_comment_strips_and_accepts_max_length():
    text = "a" * FEEDBACK_COMMENT_MAX_LENGTH
    assert normalize_feedback_comment(f"  {text}  ") == text


def test_normalize_feedback_comment_rejects_over_max_length():
    with pytest.raises(ValidationError):
        normalize_feedback_comment("x" * (FEEDBACK_COMMENT_MAX_LENGTH + 1))


def test_normalize_feedback_comment_returns_none_for_blank():
    assert normalize_feedback_comment(None) is None
    assert normalize_feedback_comment("   ") is None
