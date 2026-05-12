"""Unit tests for Slack endpoint scope keys and auth metadata parsing."""

from apps.tenant_app_service.slack.domain import slack_auth_metadata, slack_endpoint_scope_key


def test_slack_endpoint_scope_key_with_app_id():
    assert slack_endpoint_scope_key(team_id="T123", app_id="A456", tenant_id=2) == "slack:T123:A456"


def test_slack_endpoint_scope_key_without_app_id():
    assert slack_endpoint_scope_key(team_id="T123", app_id=None, tenant_id=2) == "slack:T123"


def test_slack_auth_metadata_extracts_app_id():
    team_id, app_id, bot_user_id = slack_auth_metadata(
        {"ok": True, "team_id": "T1", "api_app_id": "A1", "user_id": "U1"}
    )
    assert team_id == "T1"
    assert app_id == "A1"
    assert bot_user_id == "U1"
