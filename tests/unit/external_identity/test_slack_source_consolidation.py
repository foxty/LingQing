"""Unit tests for Slack identity source consolidation."""

from apps.shared.external_identity.domain import (
    is_slack_tenant_placeholder_source_key,
    slack_team_id_from_source_key,
    slack_workspace_source_key,
)


def test_is_slack_tenant_placeholder_source_key():
    assert is_slack_tenant_placeholder_source_key("slack:tenant:2", 2) is True
    assert is_slack_tenant_placeholder_source_key("slack:T123", 2) is False


def test_slack_team_id_from_source_key():
    assert slack_team_id_from_source_key("slack:T033XT1NE") == "T033XT1NE"
    assert slack_team_id_from_source_key("slack:tenant:2") is None
    assert slack_team_id_from_source_key("oidc:3") is None


def test_slack_workspace_source_key_roundtrip():
    assert slack_workspace_source_key(team_id="T123", tenant_id=2) == "slack:T123"
    assert slack_workspace_source_key(team_id=None, tenant_id=2) == "slack:tenant:2"
