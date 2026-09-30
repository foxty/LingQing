"""Unit tests for DocumentSourceProviderRepository."""

from __future__ import annotations

import pytest

from apps.shared.document.source_provider_repository import DocumentSourceProviderRepository
from apps.shared.document.sync_types import DEFAULT_DOCUMENT_SOURCE_PROVIDER
from tests.helpers.document_sync_fixtures import create_google_drive_provider, create_tenant_and_user

pytestmark = pytest.mark.asyncio


async def test_provider_secret_encrypted_at_rest(async_db_session):
    tenant, _user = await create_tenant_and_user(async_db_session, tenant_name="sync_t1", username="admin1")
    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)

    assert provider.config_json.get("client_secret") != "test-client-secret"

    repo = DocumentSourceProviderRepository(async_db_session)
    decrypted = repo.decrypt_config(provider)
    assert decrypted["client_id"] == "test-client-id"
    assert decrypted["client_secret"] == "test-client-secret"


async def test_upsert_provider_updates_existing_row(async_db_session):
    tenant, _user = await create_tenant_and_user(async_db_session, tenant_name="sync_t2", username="admin2")
    repo = DocumentSourceProviderRepository(async_db_session)

    first = await repo.upsert_provider(
        tenant_id=tenant.id,
        provider=DEFAULT_DOCUMENT_SOURCE_PROVIDER,
        enabled=True,
        config={"client_id": "id-1", "client_secret": "secret-1"},
    )
    second = await repo.upsert_provider(
        tenant_id=tenant.id,
        provider=DEFAULT_DOCUMENT_SOURCE_PROVIDER,
        enabled=False,
        config={"client_id": "id-2", "client_secret": "secret-2"},
    )

    assert first.id == second.id
    assert second.enabled is False
    decrypted = repo.decrypt_config(second)
    assert decrypted["client_id"] == "id-2"


async def test_get_provider_by_id_scoped_to_tenant(async_db_session):
    tenant_a, _ = await create_tenant_and_user(async_db_session, tenant_name="sync_ta", username="a")
    tenant_b, _ = await create_tenant_and_user(async_db_session, tenant_name="sync_tb", username="b")
    provider_a = await create_google_drive_provider(async_db_session, tenant_id=tenant_a.id)

    repo = DocumentSourceProviderRepository(async_db_session)
    assert await repo.get_provider_by_id(tenant_a.id, provider_a.id) is not None
    assert await repo.get_provider_by_id(tenant_b.id, provider_a.id) is None
