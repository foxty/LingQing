import json
from datetime import UTC, datetime, timedelta

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.oauth.state import OAuthStateCodec
from apps.shared.utils.field_cipher import FieldCipher


def test_oauth_state_round_trip_binds_actor_and_connector():
    codec = OAuthStateCodec(FieldCipher("synthetic-test-key"))

    state, verifier = codec.issue(
        tenant_id=11,
        user_id=22,
        resource_id=33,
        redirect_uri="https://portal.example.test/oauth/callback",
    )
    decoded = codec.decode(state)

    assert decoded.tenant_id == 11
    assert decoded.user_id == 22
    assert decoded.resource_type == RESOURCE_TYPE_API_CONNECTOR
    assert decoded.resource_id == 33
    assert decoded.code_verifier == verifier
    assert "=" not in codec.code_challenge(verifier)


def test_oauth_state_supports_data_source_resource_type():
    codec = OAuthStateCodec(FieldCipher("synthetic-test-key"))

    state, _verifier = codec.issue(
        tenant_id=5,
        user_id=7,
        resource_type=RESOURCE_TYPE_DATA_SOURCE,
        resource_id=91,
        redirect_uri="https://api.example.test/integrations/oauth/callback",
    )
    decoded = codec.decode(state)

    assert decoded.resource_type == RESOURCE_TYPE_DATA_SOURCE
    assert decoded.resource_id == 91


def test_oauth_state_decodes_legacy_connector_id_payload():
    cipher = FieldCipher("synthetic-legacy-key")
    codec = OAuthStateCodec(cipher)
    legacy_payload = {
        "tenant_id": 3,
        "user_id": 4,
        "connector_id": 55,
        "redirect_uri": "https://api.example.test/integrations/oauth/callback",
        "code_verifier": "legacy-verifier",
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    }
    legacy_state = cipher.encrypt(json.dumps(legacy_payload))

    decoded = codec.decode(legacy_state)

    assert decoded.resource_type == RESOURCE_TYPE_API_CONNECTOR
    assert decoded.resource_id == 55


def test_oauth_state_rejects_unencrypted_payload():
    codec = OAuthStateCodec(FieldCipher("synthetic-test-key"))
    forged = json.dumps(
        {
            "tenant_id": 1,
            "user_id": 2,
            "resource_type": RESOURCE_TYPE_API_CONNECTOR,
            "resource_id": 3,
            "redirect_uri": "https://api.example.test/integrations/oauth/callback",
            "code_verifier": "attacker-controlled",
            "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        }
    )

    with pytest.raises(ValidationError, match="Invalid OAuth state"):
        codec.decode(forged)


def test_oauth_state_rejects_tampered_ciphertext():
    codec = OAuthStateCodec(FieldCipher("synthetic-test-key"))
    state, _verifier = codec.issue(
        tenant_id=1,
        user_id=2,
        resource_id=3,
        redirect_uri="https://api.example.test/integrations/oauth/callback",
    )

    with pytest.raises(ValidationError, match="Invalid encrypted field"):
        codec.decode(f"{state[:-1]}x")
