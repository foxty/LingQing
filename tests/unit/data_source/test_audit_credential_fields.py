from apps.shared.external_systems.data_source.sensitive_config import datasource_audit_credential_field_names


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