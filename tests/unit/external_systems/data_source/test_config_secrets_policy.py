"""Data source config secret policy invariants."""

from apps.shared.external_systems.data_source.config_secrets_policy import DATA_SOURCE_CONFIG_POLICY


def test_user_mode_strip_includes_identity_and_merge_leaves():
    strip = DATA_SOURCE_CONFIG_POLICY.user_mode_strip_top_level
    assert "password" in strip
    assert "client_secret" in strip
    assert "username" in strip
    assert DATA_SOURCE_CONFIG_POLICY.template_strip is not None
    assert ("user_oauth",) in DATA_SOURCE_CONFIG_POLICY.template_strip.retain_subtrees