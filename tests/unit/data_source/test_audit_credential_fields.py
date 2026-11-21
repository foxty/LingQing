from apps.shared.audit_event.payload_builders import build_datasource_create_payload
from apps.shared.external_systems.data_source.sensitive_config import datasource_audit_credential_field_names


def _credentials_present_for_create_audit(config: dict) -> bool:
    """Same predicate as ``DataSourceService`` uses for ``record_datasource_create``."""
    return bool(datasource_audit_credential_field_names(config))


def test_nested_metadata_sync_password_detected():
    config = {
        "host": "localhost",
        "port": 5432,
        "database": "app",
        "metadata_sync": {"username": "sync", "password": "secret"},
    }
    fields = datasource_audit_credential_field_names(config)
    assert "metadata_sync.password" in fields


def test_top_level_password_detected():
    config = {"host": "localhost", "password": "secret"}
    assert datasource_audit_credential_field_names(config) == ["password"]


def test_host_only_config_has_no_credential_fields():
    config = {"host": "localhost", "port": 5432}
    assert datasource_audit_credential_field_names(config) == []


def test_create_audit_credentials_present_false_public_database_config():
    """Non-empty config with no credential leaves must not set credentials_present."""
    config = {"host": "localhost", "port": 5432, "database": "app"}
    assert _credentials_present_for_create_audit(config) is False
    payload = build_datasource_create_payload(
        name="warehouse",
        connector_type="postgresql",
        credentials_present=_credentials_present_for_create_audit(config),
    )
    assert payload["credentials_present"] is False


def test_create_audit_credentials_present_true_nested_metadata_sync_password_only():
    config = {"metadata_sync": {"password": "secret"}}
    assert _credentials_present_for_create_audit(config) is True
    payload = build_datasource_create_payload(
        name="sync",
        connector_type="postgresql",
        credentials_present=_credentials_present_for_create_audit(config),
    )
    assert payload["credentials_present"] is True


def test_create_audit_credentials_present_false_smtp_host_without_auth():
    config = {"host": "smtp.example.com", "port": 25}
    assert _credentials_present_for_create_audit(config) is False