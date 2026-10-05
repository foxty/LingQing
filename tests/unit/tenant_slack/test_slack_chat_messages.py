"""Unit tests for Slack chat error user-facing messages."""

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError, ValidationError
from apps.tenant_app_service.agent_ingress.slack.messages import slack_chat_error_message


def test_slack_chat_error_message_agent_access_denied():
    msg = slack_chat_error_message(AuthorizationError("无权访问该智能体"))
    assert "don't have permission to use this agent" in msg
    assert "admin" in msg


def test_slack_chat_error_message_generic_authorization():
    msg = slack_chat_error_message(AuthorizationError("Forbidden"))
    assert "don't have permission" in msg


def test_slack_chat_error_message_agent_not_found():
    msg = slack_chat_error_message(ResourceNotFoundError("Agent 99 not found"))
    assert "no longer available" in msg
    assert "Slack integration" in msg


def test_slack_chat_error_message_validation():
    msg = slack_chat_error_message(ValidationError("Invalid input"))
    assert "could not be processed" in msg


def test_slack_chat_error_message_unknown():
    msg = slack_chat_error_message(RuntimeError("boom"))
    assert "Sorry" in msg
