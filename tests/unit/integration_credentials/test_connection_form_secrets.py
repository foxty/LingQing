"""User integration GET/upsert secret shaping for connection forms."""

from apps.shared.external_systems.credentials.service import UserIntegrationCredentialService


def test_public_secrets_view_splits_sensitive_fields():
    public, configured = UserIntegrationCredentialService._public_secrets_view(
        {"username": "alice", "password": "secret", "host": "localhost"}
    )
    assert public == {"username": "alice", "host": "localhost"}
    assert configured == ["password"]


def test_public_secrets_view_ignores_empty_values():
    public, configured = UserIntegrationCredentialService._public_secrets_view(
        {"username": " ", "password": "x"}
    )
    assert public == {}
    assert configured == ["password"]
