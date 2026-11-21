import pytest
from sqlalchemy import select

from apps.shared.audit_event.payload_builders import build_datasource_create_payload
from apps.shared.db.models import AuditEvent
from apps.shared.external_systems.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.external_systems.data_source.schemas import DataSourceCreate
from apps.shared.external_systems.data_source.service import DataSourceService
from apps.shared.external_systems.data_source.sensitive_config import datasource_audit_credential_field_names
from tests.helpers.data_source_fixtures import create_tenant_user, seed_data_source_owner_policies


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


async def _create_and_read_present(session, tenant_id, owner_id, name, config):
    svc = DataSourceService(
        tenant_id=tenant_id,
        data_source_repo=DataSourceRepository(session),
        asset_repo=AssetMetadataRepository(session),
    )
    await svc.create_data_source(
        DataSourceCreate(name=name, type="postgres", managed=True, config=config), owner_id=owner_id
    )
    ev = (await session.execute(
        select(AuditEvent).where(AuditEvent.event_type == "datasource.create")
        .order_by(AuditEvent.id.desc())
    )).scalars().first()
    return (ev.payload or {}).get("credentials_present")


@pytest.mark.asyncio
async def test_create_audit_no_credentials_for_public_database(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="lead-t1", username="lead-owner1")
    await seed_data_source_owner_policies(async_db_session, tenant.id)
    present = await _create_and_read_present(
        async_db_session, tenant.id, owner.id, "public-db",
        {"host": "localhost", "port": 5432, "database": "app"},
    )
    assert present is False


@pytest.mark.asyncio
async def test_create_audit_nested_metadata_sync_password_only(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="lead-t2", username="lead-owner2")
    await seed_data_source_owner_policies(async_db_session, tenant.id, base_id=9100)
    present = await _create_and_read_present(
        async_db_session, tenant.id, owner.id, "nested-db",
        {"connection_url": "postgresql://u:p@h:5432/db", "metadata_sync": {"enabled": True, "password": "x"}},
    )
    assert present is True