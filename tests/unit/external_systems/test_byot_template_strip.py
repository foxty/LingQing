"""Unit tests for BYOT template strip helpers."""

from apps.shared.external_systems.byot_template_strip import (
    strip_connector_auth_user_mode_template,
)


def test_strip_connector_oauth2_drops_actor_tokens_only():
    auth = {
        "client_id": "app",
        "client_secret": "shared",
        "access_token": "user",
        "refresh_token": "user-r",
        "token": "t",
    }
    stripped = strip_connector_auth_user_mode_template(auth, auth_type="oauth2")
    assert stripped == {"client_id": "app", "client_secret": "shared"}


def test_strip_connector_basic_auth_drops_integration_secrets():
    auth = {"username": "u", "password": "p", "api_key": "k"}
    stripped = strip_connector_auth_user_mode_template(auth, auth_type="basic")
    assert stripped == {"username": "u"}