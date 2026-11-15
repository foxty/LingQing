"""Infrastructure adapter: public API mapping from DB entity."""

from datetime import UTC, datetime

from apps.shared.db.models import DataSource
from apps.shared.external_systems.data_source.adapters import (
    db_data_source_to_public_api_response,
    redact_data_source_config_for_api,
)


def test_redact_masks_nested_sync_password_for_api():
    redacted, paths = redact_data_source_config_for_api(
        {"metadata_sync": {"username": "u", "password": "x"}, "password": "y"}
    )
    assert "*" in redacted["metadata_sync"]["password"]
    assert "*" in redacted["password"]
    assert redacted["metadata_sync"]["password"].startswith("x"[0] if len("x") > 4 else "")
    assert paths == ["config.metadata_sync.password", "config.password"]


def test_db_data_source_to_public_api_response_redacts_metadata_sync_password():
    entity = DataSource(
        id=1,
        tenant_id=1,
        name="ds",
        type="postgres",
        managed=False,
        config={
            "type": "postgres",
            "host": "h",
            "database": "db",
            "username": "u",
            "password": "p",
            "metadata_sync": {"username": "sync", "password": "secret"},
        },
        owner_id=1,
        asset_count=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    response = db_data_source_to_public_api_response(entity)
    assert response.config["metadata_sync"]["password"] == "se**et"
    assert response.config["password"] == "*"
    assert response.config["host"] == "h"
    assert response.masked_fields == ["config.metadata_sync.password", "config.password"]


def test_redact_lists_path_when_preview_unavailable():
    redacted, paths = redact_data_source_config_for_api({"host": "h", "password": "enc:not-valid-ciphertext"})
    assert "password" not in redacted
    assert paths == ["config.password"]
