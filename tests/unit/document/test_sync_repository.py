"""Unit tests for DocumentSyncRepository."""

from __future__ import annotations

import pytest

from apps.shared.document.sync_repository import DocumentSyncRepository, merge_connection_credentials
from tests.helpers.document_sync_fixtures import create_google_drive_provider, create_tenant_and_user


def test_merge_connection_credentials_preserves_refresh_token_when_missing():
    existing = {
        "access_token": "old-access",
        "refresh_token": "keep-me",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    update = {
        "access_token": "new-access",
        "refresh_token": "",
        "expires_at": "2099-06-01T00:00:00+00:00",
    }

    merged = merge_connection_credentials(existing, update)

    assert merged["access_token"] == "new-access"
    assert merged["refresh_token"] == "keep-me"
    assert merged["expires_at"] == "2099-06-01T00:00:00+00:00"


@pytest.mark.asyncio
async def test_oauth_state_create_and_consume(async_db_session):
    tenant, user = await create_tenant_and_user(async_db_session, tenant_name="oauth_t1", username="oauth_u1")
    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)
    repo = DocumentSyncRepository(async_db_session)

    row = await repo.create_oauth_state(
        tenant_id=tenant.id,
        user_id=user.id,
        provider_id=provider.id,
        state="state-abc",
        code_verifier="verifier-xyz",
    )
    assert row.provider_id == provider.id

    consumed = await repo.consume_oauth_state("state-abc")
    assert consumed is not None
    assert consumed.user_id == user.id
    assert consumed.provider_id == provider.id
    assert await repo.consume_oauth_state("state-abc") is None


@pytest.mark.asyncio
async def test_oauth_state_expired_not_consumed(async_db_session):
    tenant, user = await create_tenant_and_user(async_db_session, tenant_name="oauth_t2", username="oauth_u2")
    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)
    repo = DocumentSyncRepository(async_db_session)

    await repo.create_oauth_state(
        tenant_id=tenant.id,
        user_id=user.id,
        provider_id=provider.id,
        state="state-exp",
        code_verifier="verifier",
        ttl_seconds=0,
    )
    assert await repo.consume_oauth_state("state-exp") is None


@pytest.mark.asyncio
async def test_connection_upsert_by_provider_id(async_db_session):
    tenant, user = await create_tenant_and_user(async_db_session, tenant_name="conn_t1", username="conn_u1")
    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)
    repo = DocumentSyncRepository(async_db_session)

    created = await repo.upsert_connection(
        tenant_id=tenant.id,
        owner_id=user.id,
        provider_id=provider.id,
        account_email="user@test-sync.example",
        credentials={"access_token": "access-1", "refresh_token": "refresh-1"},
    )
    assert created.provider_id == provider.id
    assert repo.decrypt_credentials(created)["refresh_token"] == "refresh-1"

    updated = await repo.upsert_connection(
        tenant_id=tenant.id,
        owner_id=user.id,
        provider_id=provider.id,
        account_email="user@test-sync.example",
        credentials={"access_token": "access-2", "refresh_token": "refresh-2"},
    )
    assert updated.id == created.id
    assert repo.decrypt_credentials(updated)["access_token"] == "access-2"


@pytest.mark.asyncio
async def test_connection_upsert_preserves_refresh_token_on_reconnect(async_db_session):
    tenant, user = await create_tenant_and_user(async_db_session, tenant_name="conn_reconn", username="conn_rc")
    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)
    repo = DocumentSyncRepository(async_db_session)

    created = await repo.upsert_connection(
        tenant_id=tenant.id,
        owner_id=user.id,
        provider_id=provider.id,
        account_email="user@test-sync.example",
        credentials={"access_token": "access-1", "refresh_token": "refresh-keep"},
    )
    updated = await repo.upsert_connection(
        tenant_id=tenant.id,
        owner_id=user.id,
        provider_id=provider.id,
        account_email="user@test-sync.example",
        credentials={"access_token": "access-2", "refresh_token": ""},
    )

    assert updated.id == created.id
    creds = repo.decrypt_credentials(updated)
    assert creds["access_token"] == "access-2"
    assert creds["refresh_token"] == "refresh-keep"


@pytest.mark.asyncio
async def test_connection_credentials_encrypted_at_rest(async_db_session):
    tenant, user = await create_tenant_and_user(async_db_session, tenant_name="conn_t2", username="conn_u2")
    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)
    repo = DocumentSyncRepository(async_db_session)

    connection = await repo.upsert_connection(
        tenant_id=tenant.id,
        owner_id=user.id,
        provider_id=provider.id,
        account_email="user@test-sync.example",
        credentials={"access_token": "plain-access", "refresh_token": "plain-refresh"},
    )
    stored = connection.oauth_credentials_enc or {}
    assert stored.get("access_token") != "plain-access"
    assert stored.get("refresh_token") != "plain-refresh"


@pytest.mark.asyncio
async def test_create_connector_persists_source_folder_fields(async_db_session):
    tenant, user = await create_tenant_and_user(async_db_session, tenant_name="conn_t3", username="conn_u3")
    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)
    repo = DocumentSyncRepository(async_db_session)
    connection = await repo.upsert_connection(
        tenant_id=tenant.id,
        owner_id=user.id,
        provider_id=provider.id,
        account_email="user@test-sync.example",
        credentials={"access_token": "access", "refresh_token": "refresh"},
    )

    from tests.helpers.document_fixtures import create_document_collection

    collection = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        name="Sync Collection",
    )

    connector = await repo.create_connector(
        tenant_id=tenant.id,
        source_connection_id=connection.id,
        collection_id=collection.id,
        source_folder_id="folder-123",
        source_folder_name="Quarterly Reports",
        include_subfolders=True,
    )
    assert connector.source_connection_id == connection.id
    assert connector.source_folder_id == "folder-123"
    assert connector.source_folder_name == "Quarterly Reports"


@pytest.mark.asyncio
async def test_stop_connectors_for_connection(async_db_session):
    tenant, user = await create_tenant_and_user(async_db_session, tenant_name="conn_t4", username="conn_u4")
    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)
    repo = DocumentSyncRepository(async_db_session)
    connection = await repo.upsert_connection(
        tenant_id=tenant.id,
        owner_id=user.id,
        provider_id=provider.id,
        account_email="user@test-sync.example",
        credentials={"access_token": "access", "refresh_token": "refresh"},
    )

    from tests.helpers.document_fixtures import create_document_collection

    collection = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        name="Stop Sync Collection",
    )
    connector = await repo.create_connector(
        tenant_id=tenant.id,
        source_connection_id=connection.id,
        collection_id=collection.id,
        source_folder_id="folder-stop",
        source_folder_name="Stop Folder",
        include_subfolders=True,
    )

    await repo.stop_connectors_for_connection(tenant.id, connection.id)
    await async_db_session.refresh(connector)
    assert connector.status == "stopped"


@pytest.mark.asyncio
async def test_list_drive_linked_document_ids_scoped_to_collection(async_db_session):
    tenant, user = await create_tenant_and_user(async_db_session, tenant_name="drive_ids_t1", username="drive_ids_u1")
    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)
    repo = DocumentSyncRepository(async_db_session)
    connection = await repo.upsert_connection(
        tenant_id=tenant.id,
        owner_id=user.id,
        provider_id=provider.id,
        account_email="user@test-sync.example",
        credentials={"access_token": "access", "refresh_token": "refresh"},
    )

    from tests.helpers.document_fixtures import create_document, create_document_collection

    collection_a = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        name="Collection A",
    )
    collection_b = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        name="Collection B",
    )
    drive_doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection_a.id,
        filename="drive-synced.pdf",
        file_hash="hash-drive",
    )
    upload_doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection_a.id,
        filename="manual-upload.pdf",
        file_hash="hash-upload",
    )
    other_collection_doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection_b.id,
        filename="other.pdf",
        file_hash="hash-other",
    )

    connector_a = await repo.create_connector(
        tenant_id=tenant.id,
        source_connection_id=connection.id,
        collection_id=collection_a.id,
        source_folder_id="folder-a",
        source_folder_name="Folder A",
        include_subfolders=True,
    )
    connector_b = await repo.create_connector(
        tenant_id=tenant.id,
        source_connection_id=connection.id,
        collection_id=collection_b.id,
        source_folder_id="folder-b",
        source_folder_name="Folder B",
        include_subfolders=True,
    )

    await repo.create_external_file(
        tenant_id=tenant.id,
        connector_id=connector_a.id,
        document_id=drive_doc.id,
        external_file_id="ext-a",
        external_name="drive-synced.pdf",
        external_modified_at=None,
    )
    await repo.create_external_file(
        tenant_id=tenant.id,
        connector_id=connector_b.id,
        document_id=other_collection_doc.id,
        external_file_id="ext-b",
        external_name="other.pdf",
        external_modified_at=None,
    )
    await async_db_session.commit()

    linked = await repo.list_drive_linked_document_ids(tenant.id, collection_a.id)

    assert linked == {drive_doc.id}
    assert upload_doc.id not in linked

    paged = await repo.list_drive_linked_document_ids(
        tenant.id,
        collection_a.id,
        document_ids=[upload_doc.id, drive_doc.id, other_collection_doc.id],
    )
    assert paged == {drive_doc.id}

    assert await repo.list_drive_linked_document_ids(tenant.id, collection_a.id, document_ids=[]) == set()


@pytest.mark.asyncio
async def test_purge_expired_oauth_states(async_db_session):
    tenant, user = await create_tenant_and_user(async_db_session, tenant_name="oauth_t3", username="oauth_u3")
    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)
    repo = DocumentSyncRepository(async_db_session)

    await repo.create_oauth_state(
        tenant_id=tenant.id,
        user_id=user.id,
        provider_id=provider.id,
        state="expired-state",
        code_verifier="verifier",
        ttl_seconds=0,
    )
    purged = await repo.purge_expired_oauth_states(tenant_id=tenant.id)
    assert purged >= 1
    assert await repo.consume_oauth_state("expired-state") is None
