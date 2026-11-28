"""Pack version and pack_ref helper tests."""

from apps.shared.external_systems.packs.versioning import (
    pack_id_from_ref,
    pack_update_metadata,
    pack_version_is_behind,
)


def test_pack_id_from_ref_parses_major_suffix():
    assert pack_id_from_ref("slack-user@1") == "slack-user"
    assert pack_id_from_ref("github-user@2") == "github-user"
    assert pack_id_from_ref(None) is None


def test_pack_version_is_behind_treats_missing_installed_as_stale():
    assert pack_version_is_behind(None, "1.2.0") is True
    assert pack_version_is_behind("", "1.2.0") is True


def test_pack_version_is_behind_compares_semver():
    assert pack_version_is_behind("1.1.1", "1.2.0") is True
    assert pack_version_is_behind("1.2.0", "1.2.0") is False
    assert pack_version_is_behind("2.0.0", "1.9.9") is False


def test_pack_catalog_metadata_marks_builtin_slack_behind_when_installed_old():
    catalog_version, update_available = pack_update_metadata(
        pack_ref="slack-user@1",
        installed_pack_version="1.0.0",
    )
    assert catalog_version == "1.2.0"
    assert update_available is True