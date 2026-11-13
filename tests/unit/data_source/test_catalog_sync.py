"""Domain: catalog sync credentials and user-mode config template rules."""

from apps.shared.external_systems.data_source.catalog_sync import (
    API_SECRET_PLACEHOLDER,
    CatalogSyncCredentials,
    strip_user_mode_connection_template,
)
def test_merge_connection_config_combines_template_and_sync_block():
    raw = {
        "host": "localhost",
        "database": "app",
        "metadata_sync": {"username": "sync_u", "password": "sync_p"},
    }
    merged = CatalogSyncCredentials.merge_connection_config(raw)
    assert merged["host"] == "localhost"
    assert merged["username"] == "sync_u"
    assert merged["password"] == "sync_p"
    assert "metadata_sync" not in merged


def test_is_configured_in_config_requires_username_for_postgres():
    assert CatalogSyncCredentials.is_configured_in_config(
        {"metadata_sync": {"username": "u", "password": "p"}},
        data_source_type="postgres",
    )
    assert not CatalogSyncCredentials.is_configured_in_config(
        {"metadata_sync": {"password": "p"}},
        data_source_type="postgres",
    )


def test_merge_incoming_into_config_preserves_password_on_placeholder():
    existing = {"host": "h", "metadata_sync": {"username": "u", "password": "secret"}}
    incoming = {"host": "h2", "metadata_sync": {"username": "u2", "password": API_SECRET_PLACEHOLDER}}
    merged = CatalogSyncCredentials.merge_incoming_into_config(existing, incoming)
    assert merged["host"] == "h2"
    assert merged["metadata_sync"]["username"] == "u2"
    assert merged["metadata_sync"]["password"] == "secret"


def test_merge_incoming_into_config_preserves_root_password_on_placeholder():
    existing = {"host": "h", "username": "u", "password": "secret-root"}
    incoming = {"host": "h2", "password": API_SECRET_PLACEHOLDER}
    merged = CatalogSyncCredentials.merge_incoming_into_config(existing, incoming)
    assert merged["host"] == "h2"
    assert merged["password"] == "secret-root"


def test_strip_user_mode_connection_template_removes_credentials_keeps_endpoint():
    raw = {
        "readOnly": True,
        "host": "localhost",
        "port": 5432,
        "database": "lq_tenant_app",
        "username": "u",
        "password": "p",
        "connection_url": "postgresql://u:p@localhost/db",
    }
    stripped = strip_user_mode_connection_template(raw)
    assert stripped == {
        "readOnly": True,
        "host": "localhost",
        "port": 5432,
        "database": "lq_tenant_app",
    }

