"""Unit tests for Slack identity user-facing messages."""

from apps.tenant_app_service.agent_ingress.slack.messages import slack_identity_user_message


def test_slack_identity_user_message_reject_unknown():
    msg = slack_identity_user_message(action="deny", reason="policy_reject_unknown")
    assert "No LingQing account" in msg
    assert "same email" in msg


def test_slack_identity_user_message_missing_email():
    msg = slack_identity_user_message(action="deny", reason="missing_email")
    assert "could not read an email" in msg.lower()


def test_slack_identity_user_message_pending():
    msg = slack_identity_user_message(action="pending", reason="subject_pending")
    assert "pending admin approval" in msg
