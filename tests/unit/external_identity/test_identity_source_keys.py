"""Unit tests for identity source domain keys."""

from apps.shared.external_identity.domain import (
    IdentitySourceKind,
    login_provider_source_key,
    slack_workspace_source_key,
)


def test_login_provider_source_key():
    assert login_provider_source_key(3) == "oidc:3"


def test_slack_workspace_source_key_with_team():
    assert slack_workspace_source_key(team_id="T123", tenant_id=2) == "slack:T123"


def test_slack_workspace_source_key_without_team_falls_back_to_tenant():
    assert slack_workspace_source_key(team_id=None, tenant_id=2) == "slack:tenant:2"


def test_identity_source_kind_values_match_db_strings():
    assert IdentitySourceKind.LOGIN_PROVIDER == "login_provider"
    assert IdentitySourceKind.CHANNEL_WORKSPACE == "channel_workspace"
