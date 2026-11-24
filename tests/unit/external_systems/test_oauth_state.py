from apps.shared.external_systems.oauth.state import OAuthStateCodec
from apps.shared.utils.field_cipher import FieldCipher


def test_oauth_state_round_trip_binds_actor_and_connector():
    codec = OAuthStateCodec(FieldCipher("synthetic-test-key"))

    state, verifier = codec.issue(
        tenant_id=11,
        user_id=22,
        connector_id=33,
        redirect_uri="https://portal.example.test/oauth/callback",
    )
    decoded = codec.decode(state)

    assert decoded.tenant_id == 11
    assert decoded.user_id == 22
    assert decoded.connector_id == 33
    assert decoded.code_verifier == verifier
    assert "=" not in codec.code_challenge(verifier)
