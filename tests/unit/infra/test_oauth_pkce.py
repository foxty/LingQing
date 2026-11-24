from apps.shared.infra.oauth.pkce import code_challenge, generate_pkce


def test_generate_pkce_returns_s256_challenge():
    state, verifier, challenge = generate_pkce()
    assert state
    assert verifier
    assert challenge == code_challenge(verifier)
