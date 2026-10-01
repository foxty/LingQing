"""Unit tests for document list intake_source enrichment."""

from __future__ import annotations

from uuid import uuid4

import pytest

from apps.shared.document.service import DocumentService
from apps.shared.document.sync_repository import DocumentSyncRepository
from tests.helpers.document_fixtures import create_document, create_document_collection, create_tenant_user
from tests.helpers.document_sync_fixtures import create_google_drive_provider, create_tenant_and_user


@pytest.mark.asyncio
async def test_list_documents_marks_drive_linked_as_drive_sync(async_db_session):
    tenant, user = await create_tenant_and_user(
        async_db_session,
        tenant_name=f"intake_src_{uuid4().hex[:6]}",
        username=f"intake_user_{uuid4().hex[:6]}",
    )
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id)
    upload_doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="manual-upload.pdf",
        file_hash=f"hash-upload-{uuid4().hex[:8]}",
    )
    drive_doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="drive-synced.pdf",
        file_hash=f"hash-drive-{uuid4().hex[:8]}",
    )

    provider = await create_google_drive_provider(async_db_session, tenant_id=tenant.id)
    repo = DocumentSyncRepository(async_db_session)
    connection = await repo.upsert_connection(
        tenant_id=tenant.id,
        owner_id=user.id,
        provider_id=provider.id,
        account_email=f"user-{uuid4().hex[:6]}@test-sync.example",
        credentials={"access_token": "access", "refresh_token": "refresh"},
    )
    connector = await repo.create_connector(
        tenant_id=tenant.id,
        source_connection_id=connection.id,
        collection_id=collection.id,
        source_folder_id="folder-a",
        source_folder_name="Folder A",
        include_subfolders=True,
    )
    await repo.create_external_file(
        tenant_id=tenant.id,
        connector_id=connector.id,
        document_id=drive_doc.id,
        external_file_id="ext-drive",
        external_name="drive-synced.pdf",
        external_modified_at=None,
    )

    service = DocumentService(tenant_id=tenant.id, db_session=async_db_session, file_storage=object())
    docs, _pagination = await service.list_documents(
        requester_id=user.id,
        requester_role=user.role,
        page=1,
        page_size=10,
        query=None,
        collection_id=collection.id,
    )

    by_id = {doc.id: doc for doc in docs}
    assert by_id[upload_doc.id].intake_source == "upload"
    assert by_id[upload_doc.id].external_file_id is None
    assert by_id[drive_doc.id].intake_source == "drive_sync"
    assert by_id[drive_doc.id].external_file_id == "ext-drive"


@pytest.mark.asyncio
async def test_list_documents_without_collection_defaults_to_upload(async_db_session):
    tenant, user = await create_tenant_user(async_db_session, tenant_name="intake_default", username="intake_default")
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id)
    doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="plain.pdf",
        file_hash=f"hash-plain-{uuid4().hex[:8]}",
    )

    service = DocumentService(tenant_id=tenant.id, db_session=async_db_session, file_storage=object())
    docs, _pagination = await service.list_documents(
        requester_id=user.id,
        requester_role=user.role,
        page=1,
        page_size=10,
        query=None,
    )

    matched = next(item for item in docs if item.id == doc.id)
    assert matched.intake_source == "upload"
    assert matched.external_file_id is None
