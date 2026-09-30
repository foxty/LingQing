"""Integration tests for document source sync (Google Drive v1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from apps.shared.db.models import DocumentSourceConnection, DocumentSyncConnector
from apps.shared.document.sync_repository import DocumentSyncRepository
from apps.shared.infra.external_files.port import ExternalFileEntry
from apps.tenant_app_service.server import app
from tests.helpers.document_fixtures import create_document, create_document_collection
from tests.integration.conftest import make_auth_headers
from tests.integration.helpers.document_sync_helpers import (
    clear_test_client_overrides,
    configure_google_drive_source,
    grant_collection_acl,
    seed_document_sync_tenant,
    seed_owner_only_collection_abac,
    wire_test_client,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def document_sync_setup(pg_async_db_session):
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    connection = await pg_async_db_session.connection()
    session_factory = async_sessionmaker(
        bind=connection,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )

    async with session_factory() as seed_session:
        setup = await seed_document_sync_tenant(seed_session)
        await seed_session.commit()

    await wire_test_client(session_factory)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        setup["client"] = client
        setup["session_factory"] = session_factory
        yield setup

    clear_test_client_overrides()


class TestDocumentSourceSyncFlow:
    async def test_admin_can_configure_google_drive_source(self, document_sync_setup):
        client = document_sync_setup["client"]
        token = document_sync_setup["admin_token"]

        await configure_google_drive_source(client, token)

        resp = await client.get("/document-sources/google-drive", headers=make_auth_headers(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["enabled"] is True
        assert body["client_id"] == "integration-client-id"
        assert body["client_secret_configured"] is True

    async def test_member_cannot_configure_google_drive_source(self, document_sync_setup):
        client = document_sync_setup["client"]
        resp = await client.put(
            "/document-sources/google-drive",
            json={
                "client_id": "blocked",
                "client_secret": "blocked",
                "enabled": True,
            },
            headers=make_auth_headers(document_sync_setup["member_token"]),
        )
        assert resp.status_code == 403

    async def test_oauth_callback_creates_connection_with_provider_id(self, document_sync_setup):
        client = document_sync_setup["client"]
        admin_token = document_sync_setup["admin_token"]
        tenant_id = document_sync_setup["tenant"].id
        member = document_sync_setup["member"]

        await configure_google_drive_source(client, admin_token)

        authorize_resp = await client.get(
            "/document-sync/google/authorize",
            headers=make_auth_headers(document_sync_setup["member_token"]),
        )
        assert authorize_resp.status_code == 200, authorize_resp.text
        authorize_url = authorize_resp.json()["authorize_url"]
        state = parse_qs(urlparse(authorize_url).query)["state"][0]

        token_payload = {
            "access_token": "drive-access-token",
            "refresh_token": "drive-refresh-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        with (
            patch(
                "apps.shared.document.sync_service.GoogleDriveClient.exchange_code",
                new=AsyncMock(return_value=token_payload),
            ),
            patch(
                "apps.shared.document.sync_service.GoogleDriveClient.get_account_email",
                new=AsyncMock(return_value="member@test-sync.example"),
            ),
        ):
            callback_resp = await client.get(
                "/document-sync/google/callback",
                params={"state": state, "code": "auth-code"},
                follow_redirects=False,
            )
        assert callback_resp.status_code in (302, 307), callback_resp.text

        connections_resp = await client.get(
            "/document-sync/connections",
            headers=make_auth_headers(document_sync_setup["member_token"]),
        )
        assert connections_resp.status_code == 200, connections_resp.text
        connections = connections_resp.json()
        assert len(connections) == 1
        assert connections[0]["provider"] == "google_drive"
        assert connections[0]["provider_id"] > 0
        assert connections[0]["account_email"] == "member@test-sync.example"

        async with document_sync_setup["session_factory"]() as session:
            row = await session.get(DocumentSourceConnection, connections[0]["id"])
            assert row is not None
            assert row.tenant_id == tenant_id
            assert row.owner_id == member.id
            assert row.provider_id == connections[0]["provider_id"]

    async def test_bind_folder_and_manual_sync(self, document_sync_setup):
        client = document_sync_setup["client"]
        admin_token = document_sync_setup["admin_token"]
        member_token = document_sync_setup["member_token"]
        tenant = document_sync_setup["tenant"]
        member = document_sync_setup["member"]

        await configure_google_drive_source(client, admin_token)

        async with document_sync_setup["session_factory"]() as session:
            from tests.helpers.document_sync_fixtures import create_google_drive_provider

            provider = await create_google_drive_provider(session, tenant_id=tenant.id)
            repo = DocumentSyncRepository(session)
            connection = await repo.upsert_connection(
                tenant_id=tenant.id,
                owner_id=member.id,
                provider_id=provider.id,
                account_email=f"member-{uuid4().hex[:6]}@test-sync.example",
                credentials={
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_at": "2099-01-01T00:00:00+00:00",
                },
            )
            collection = await create_document_collection(
                session,
                tenant_id=tenant.id,
                owner_id=member.id,
                name=f"Sync Collection {uuid4().hex[:6]}",
            )
            document = await create_document(
                session,
                tenant_id=tenant.id,
                owner_id=member.id,
                collection_id=collection.id,
                filename="brief.pdf",
                file_hash=f"hash-{uuid4().hex[:8]}",
            )
            await session.commit()
            connection_id = connection.id
            collection_id = collection.id
            document_id = document.id

        create_resp = await client.post(
            f"/document-collections/{collection_id}/sync-connector",
            json={
                "source_connection_id": connection_id,
                "source_folder_id": "folder-abc",
                "source_folder_name": "Reports",
                "include_subfolders": True,
            },
            headers=make_auth_headers(member_token),
        )
        assert create_resp.status_code == 201, create_resp.text
        connector = create_resp.json()
        assert connector["source_folder_id"] == "folder-abc"
        assert connector["source_connection_id"] == connection_id

        remote_entry = ExternalFileEntry(
            external_id="remote-file-1",
            name="brief.pdf",
            mime_type="application/pdf",
            modified_at=None,
            parent_folder_id="folder-abc",
        )

        with (
            patch(
                "apps.shared.document.sync_service.GoogleDriveClient.list_folder_tree",
                new=AsyncMock(return_value=[remote_entry]),
            ),
            patch(
                "apps.shared.document.sync_service.GoogleDriveClient.download_file",
                new=AsyncMock(return_value=("brief.pdf", b"%PDF-1.4 test")),
            ),
            patch(
                "apps.shared.document.sync_service.DocumentSyncService._intake_remote_file",
                new=AsyncMock(return_value=type("Doc", (), {"id": document_id})()),
            ),
        ):
            sync_resp = await client.post(
                f"/document-sync/connectors/{connector['id']}/sync",
                headers=make_auth_headers(member_token),
            )
        assert sync_resp.status_code == 200, sync_resp.text
        result = sync_resp.json()
        assert result["added"] == 1

    async def test_disconnect_connection_stops_connector(self, document_sync_setup):
        client = document_sync_setup["client"]
        tenant = document_sync_setup["tenant"]
        member = document_sync_setup["member"]
        member_token = document_sync_setup["member_token"]

        async with document_sync_setup["session_factory"]() as session:
            from tests.helpers.document_sync_fixtures import create_google_drive_provider

            provider = await create_google_drive_provider(session, tenant_id=tenant.id)
            repo = DocumentSyncRepository(session)
            connection = await repo.upsert_connection(
                tenant_id=tenant.id,
                owner_id=member.id,
                provider_id=provider.id,
                account_email=f"member-{uuid4().hex[:6]}@test-sync.example",
                credentials={"access_token": "access", "refresh_token": "refresh"},
            )
            collection = await create_document_collection(
                session,
                tenant_id=tenant.id,
                owner_id=member.id,
                name=f"Disconnect Collection {uuid4().hex[:6]}",
            )
            connector = await repo.create_connector(
                tenant_id=tenant.id,
                source_connection_id=connection.id,
                collection_id=collection.id,
                source_folder_id="folder-x",
                source_folder_name="Folder X",
                include_subfolders=True,
            )
            await session.commit()
            connection_id = connection.id
            connector_id = connector.id

        delete_resp = await client.delete(
            f"/document-sync/connections/{connection_id}",
            headers=make_auth_headers(member_token),
        )
        assert delete_resp.status_code == 204, delete_resp.text

        connections_resp = await client.get(
            "/document-sync/connections",
            headers=make_auth_headers(member_token),
        )
        assert connections_resp.status_code == 200, connections_resp.text
        assert connections_resp.json() == []

        async with document_sync_setup["session_factory"]() as session:
            connection_row = await session.get(DocumentSourceConnection, connection_id)
            connector_row = await session.get(DocumentSyncConnector, connector_id)
            assert connection_row.status == "revoked"
            assert connector_row.status == "stopped"

    async def test_shared_collection_sync_acl(self, document_sync_setup):
        client = document_sync_setup["client"]
        tenant = document_sync_setup["tenant"]
        member = document_sync_setup["member"]
        viewer = document_sync_setup["viewer"]
        member_token = document_sync_setup["member_token"]
        viewer_token = document_sync_setup["viewer_token"]

        async with document_sync_setup["session_factory"]() as session:
            from tests.helpers.document_sync_fixtures import create_google_drive_provider

            await seed_owner_only_collection_abac(session, tenant_id=tenant.id, created_by=member.id)
            provider = await create_google_drive_provider(session, tenant_id=tenant.id)
            repo = DocumentSyncRepository(session)
            connection = await repo.upsert_connection(
                tenant_id=tenant.id,
                owner_id=member.id,
                provider_id=provider.id,
                account_email=f"member-{uuid4().hex[:6]}@test-sync.example",
                credentials={"access_token": "access", "refresh_token": "refresh"},
            )
            collection = await create_document_collection(
                session,
                tenant_id=tenant.id,
                owner_id=member.id,
                name=f"Shared Sync Collection {uuid4().hex[:6]}",
            )
            connector = await repo.create_connector(
                tenant_id=tenant.id,
                source_connection_id=connection.id,
                collection_id=collection.id,
                source_folder_id="folder-shared",
                source_folder_name="Shared Folder",
                include_subfolders=True,
            )
            await grant_collection_acl(
                session,
                tenant_id=tenant.id,
                collection_id=collection.id,
                owner_id=member.id,
                grantee_user_id=viewer.id,
                permission="read",
                created_by=member.id,
            )
            await session.commit()
            collection_id = collection.id
            connection_id = connection.id
            connector_id = connector.id

        owner_collections = await client.get("/document-collections", headers=make_auth_headers(member_token))
        assert owner_collections.status_code == 200, owner_collections.text
        owner_row = next(item for item in owner_collections.json() if item["id"] == collection_id)
        assert owner_row["can_write"] is True
        assert owner_row["can_manage"] is True

        sharee_collections = await client.get("/document-collections", headers=make_auth_headers(viewer_token))
        assert sharee_collections.status_code == 200, sharee_collections.text
        sharee_row = next(item for item in sharee_collections.json() if item["id"] == collection_id)
        assert sharee_row["can_write"] is False
        assert sharee_row["can_manage"] is False

        get_connector_resp = await client.get(
            f"/document-collections/{collection_id}/sync-connector",
            headers=make_auth_headers(viewer_token),
        )
        assert get_connector_resp.status_code == 200, get_connector_resp.text
        assert get_connector_resp.json()["id"] == connector_id

        bind_resp = await client.post(
            f"/document-collections/{collection_id}/sync-connector",
            json={
                "source_connection_id": connection_id,
                "source_folder_id": "folder-other",
                "source_folder_name": "Other",
                "include_subfolders": True,
            },
            headers=make_auth_headers(document_sync_setup["admin_token"]),
        )
        assert bind_resp.status_code == 403, bind_resp.text

        sync_resp = await client.post(
            f"/document-sync/connectors/{connector_id}/sync",
            headers=make_auth_headers(viewer_token),
        )
        assert sync_resp.status_code == 403, sync_resp.text
