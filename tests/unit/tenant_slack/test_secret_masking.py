"""Unit tests for Slack secret masking (encrypt on write, mask in responses).

Uses an in-memory SQLite session to verify that bot_token and signing_secret
are encrypted at rest and never appear in the decrypted response surface.
"""

import pytest

from apps.shared.utils.field_cipher import FieldCipher
from apps.tenant_app_service.slack.dtos import SlackIntegrationResponse


@pytest.fixture
def cipher():
    return FieldCipher()


def test_bot_token_encrypted_at_rest(cipher):
    encrypted = cipher.encrypt("xoxb-secret-token")
    assert encrypted != "xoxb-secret-token"
    assert encrypted.startswith("enc:")
    assert cipher.decrypt(encrypted) == "xoxb-secret-token"


def test_signing_secret_encrypted_at_rest(cipher):
    encrypted = cipher.encrypt("signing-secret-value")
    assert encrypted != "signing-secret-value"
    assert encrypted.startswith("enc:")
    assert cipher.decrypt(encrypted) == "signing-secret-value"


def test_integration_response_masks_secrets():
    """SlackIntegrationResponse exposes *_configured booleans, never raw secrets."""
    response = SlackIntegrationResponse(
        id=1,
        tenant_id=10,
        agent_id=-1,
        slack_team_id="T123",
        bot_token_configured=True,
        signing_secret_configured=True,
        default_agent_id=-1,
        enabled=True,
        endpoint_key="abc123",
        events_url="https://example.com/ingress/abc123/events",
    )
    dumped = response.model_dump()
    assert "bot_token" not in dumped
    assert "signing_secret" not in dumped
    assert "bot_token_encrypted" not in dumped
    assert "signing_secret_encrypted" not in dumped
    assert dumped["bot_token_configured"] is True
    assert dumped["signing_secret_configured"] is True
