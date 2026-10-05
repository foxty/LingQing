"""Tests for Slack reply text guards."""

from apps.tenant_app_service.agent_ingress.slack.domain import ensure_slack_reply_text


def test_ensure_slack_reply_text_preserves_non_empty():
    assert ensure_slack_reply_text("hello") == "hello"


def test_ensure_slack_reply_text_uses_fallback_for_blank():
    assert ensure_slack_reply_text("  ") == "The model returned no visible text. Please try again."
