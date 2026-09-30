"""Tests for DocumentSyncService."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from apps.shared.core.exceptions import AuthorizationError, DuplicateResourceError, ValidationError
from apps.shared.domain.types import ABAC_ACTION_READ, AUTHZ_ACTION_MANAGE
from apps.shared.document.sync_schemas import CreateSyncConnectorRequest, GoogleDriveSourceConfigRequest
from apps.shared.document.sync_service import DocumentSyncService, SyncDiffResult
from apps.shared.domain.actor import ActorContext
from apps.shared.infra.external_files.port import ExternalFileEntry


@pytest.fixture
def sync_service() -> DocumentSyncService:
    service = DocumentSyncService(
        tenant_id=1,
        db_session=AsyncMock(),
        file_storage=AsyncMock(),
    )
    service._sync_repo = AsyncMock()
    service._document_repo = AsyncMock()
    return service


def _entry(external_id: str, *, modified_at: datetime | None = None) -> ExternalFileEntry:
    return ExternalFileEntry(
        external_id=external_id,
        name=f"{external_id}.pdf",
        mime_type="application/pdf",
        modified_at=modified_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_apply_sync_diff_imports_same_filename_different_drive_ids(sync_service: DocumentSyncService):
    shared_name = "report.pdf"
    remote = [
        ExternalFileEntry(
            external_id="drive-file-a",
            name=shared_name,
            mime_type="application/pdf",
            modified_at=datetime(2026, 1, 1, tzinfo=UTC),
            parent_folder_id="folder-1",
        ),
        ExternalFileEntry(
            external_id="drive-file-b",
            name=shared_name,
            mime_type="application/pdf",
            modified_at=datetime(2026, 1, 2, tzinfo=UTC),
            parent_folder_id="folder-1",
        ),
    ]
    sync_service._sync_repo.list_external_files = AsyncMock(return_value=[])
    sync_service._intake_remote_file = AsyncMock(side_effect=[MagicMock(id=10), MagicMock(id=11)])
    sync_service._sync_repo.create_external_file = AsyncMock()

    result = await sync_service._apply_sync_diff(
        connector=MagicMock(id=5, collection_id=20),
        connection=MagicMock(owner_id=7),
        drive_client=AsyncMock(),
        remote_files=remote,
    )

    assert result == SyncDiffResult(added=2, updated=0, deleted=0, skipped=0)
    assert sync_service._intake_remote_file.await_count == 2
    external_ids = {
        call.kwargs["external_file_id"]
        for call in sync_service._sync_repo.create_external_file.await_args_list
    }
    assert external_ids == {"drive-file-a", "drive-file-b"}


@pytest.mark.asyncio
async def test_apply_sync_diff_adds_new_files(sync_service: DocumentSyncService):
    remote = [_entry("file-a"), _entry("file-b")]
    sync_service._sync_repo.list_external_files = AsyncMock(return_value=[])
    sync_service._intake_remote_file = AsyncMock(side_effect=[MagicMock(id=10), MagicMock(id=11)])
    sync_service._sync_repo.create_external_file = AsyncMock()

    result = await sync_service._apply_sync_diff(
        connector=MagicMock(id=5, collection_id=20),
        connection=MagicMock(owner_id=7),
        drive_client=AsyncMock(),
        remote_files=remote,
    )

    assert result == SyncDiffResult(added=2, updated=0, deleted=0, skipped=0)
    assert sync_service._sync_repo.create_external_file.await_count == 2


@pytest.mark.asyncio
async def test_apply_sync_diff_skips_unchanged_files(sync_service: DocumentSyncService):
    modified_at = datetime(2026, 1, 1, tzinfo=UTC)
    mapping = MagicMock(
        external_file_id="file-a",
        document_id=10,
        external_modified_at=modified_at,
    )
    sync_service._sync_repo.list_external_files = AsyncMock(return_value=[mapping])

    result = await sync_service._apply_sync_diff(
        connector=MagicMock(id=5, collection_id=20),
        connection=MagicMock(owner_id=7),
        drive_client=AsyncMock(),
        remote_files=[_entry("file-a", modified_at=modified_at)],
    )

    assert result == SyncDiffResult(added=0, updated=0, deleted=0, skipped=1)


@pytest.mark.asyncio
async def test_apply_sync_diff_soft_deletes_removed_files(sync_service: DocumentSyncService):
    mapping = MagicMock(
        external_file_id="removed-file",
        document_id=42,
        external_modified_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    sync_service._sync_repo.list_external_files = AsyncMock(return_value=[mapping])
    sync_service._document_repo.soft_delete = AsyncMock(return_value=True)
    sync_service._sync_repo.clear_external_file_document = AsyncMock()

    result = await sync_service._apply_sync_diff(
        connector=MagicMock(id=5, collection_id=20),
        connection=MagicMock(owner_id=7),
        drive_client=AsyncMock(),
        remote_files=[],
    )

    assert result == SyncDiffResult(added=0, updated=0, deleted=1, skipped=0)
    sync_service._document_repo.soft_delete.assert_awaited_once_with(42, sync_service.tenant_id)
    sync_service._sync_repo.clear_external_file_document.assert_awaited_once_with(mapping)


@pytest.mark.asyncio
async def test_apply_sync_diff_updates_modified_files(sync_service: DocumentSyncService):
    mapping = MagicMock(
        external_file_id="file-a",
        document_id=10,
        external_modified_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    sync_service._sync_repo.list_external_files = AsyncMock(return_value=[mapping])
    sync_service._update_existing_document = AsyncMock(return_value=True)
    sync_service._sync_repo.update_external_file = AsyncMock()

    result = await sync_service._apply_sync_diff(
        connector=MagicMock(id=5, collection_id=20),
        connection=MagicMock(owner_id=7),
        drive_client=AsyncMock(),
        remote_files=[_entry("file-a", modified_at=datetime(2026, 2, 1, tzinfo=UTC))],
    )

    assert result == SyncDiffResult(added=0, updated=1, deleted=0, skipped=0)
    sync_service._update_existing_document.assert_awaited_once()


def test_token_needs_refresh_when_expired():
    expired = (datetime.now(UTC).replace(microsecond=0)).isoformat()
    assert DocumentSyncService._token_needs_refresh({"expires_at": expired}) is True


def test_token_needs_refresh_when_missing_expiry():
    assert DocumentSyncService._token_needs_refresh({}) is False


@pytest.mark.asyncio
async def test_get_google_drive_source_returns_configured_state(sync_service: DocumentSyncService):
    provider = MagicMock(enabled=True, provider="google_drive")
    sync_service._provider_repo.get_provider = AsyncMock(return_value=provider)
    sync_service._provider_repo.decrypt_config = MagicMock(
        return_value={"client_id": "cid", "client_secret": "secret"},
    )

    result = await sync_service.get_google_drive_source()

    assert result.enabled is True
    assert result.client_id == "cid"
    assert result.client_secret_configured is True


@pytest.mark.asyncio
async def test_upsert_google_drive_source_requires_secret_on_create(sync_service: DocumentSyncService):
    sync_service._provider_repo.get_provider = AsyncMock(return_value=None)

    with pytest.raises(ValidationError):
        await sync_service.upsert_google_drive_source(
            GoogleDriveSourceConfigRequest(client_id="cid", client_secret="", enabled=True),
        )


@pytest.mark.asyncio
async def test_start_google_authorize_creates_oauth_state_with_provider_id(sync_service: DocumentSyncService):
    provider = MagicMock(id=11, enabled=True, provider="google_drive")
    sync_service._provider_repo.get_provider = AsyncMock(return_value=provider)
    sync_service._provider_repo.decrypt_config = MagicMock(
        return_value={"client_id": "cid", "client_secret": "secret"},
    )
    sync_service._sync_repo.create_oauth_state = AsyncMock()

    with patch("apps.shared.document.sync_service.generate_pkce", return_value=("state", "verifier", "challenge")):
        result = await sync_service.start_google_authorize(user_id=7)

    assert "accounts.google.com" in result.authorize_url
    sync_service._sync_repo.create_oauth_state.assert_awaited_once_with(
        tenant_id=1,
        user_id=7,
        provider_id=11,
        state="state",
        code_verifier="verifier",
    )


@pytest.mark.asyncio
async def test_create_connector_rejects_non_owner(sync_service: DocumentSyncService):
    sync_service._collection_service.require_collection_access = AsyncMock(
        return_value=MagicMock(owner_id=1),
    )

    with pytest.raises(AuthorizationError):
        await sync_service.create_connector(
            collection_id=20,
            request=CreateSyncConnectorRequest(
                source_connection_id=3,
                source_folder_id="folder-1",
                source_folder_name="Folder",
            ),
            actor=ActorContext(tenant_id=1, user_id=7, user_role="admin"),
        )


@pytest.mark.asyncio
async def test_create_connector_rejects_duplicate(sync_service: DocumentSyncService):
    sync_service._collection_service.require_collection_access = AsyncMock(
        return_value=MagicMock(owner_id=7),
    )
    sync_service._sync_repo.get_connector_by_collection = AsyncMock(return_value=MagicMock(id=99))

    with pytest.raises(DuplicateResourceError):
        await sync_service.create_connector(
            collection_id=20,
            request=CreateSyncConnectorRequest(
                source_connection_id=3,
                source_folder_id="folder-1",
                source_folder_name="Folder",
            ),
            actor=ActorContext(tenant_id=1, user_id=7, user_role="member"),
        )

    sync_service._collection_service.require_collection_access.assert_awaited_once_with(
        collection_id=20,
        actor=ActorContext(tenant_id=1, user_id=7, user_role="member"),
        action=AUTHZ_ACTION_MANAGE,
    )


@pytest.mark.asyncio
async def test_list_connections_excludes_revoked(sync_service: DocumentSyncService):
    now = datetime(2026, 1, 1, tzinfo=UTC)

    def _connection(status: str, connection_id: int) -> MagicMock:
        return MagicMock(
            id=connection_id,
            provider_id=1,
            status=status,
            account_email=f"user-{connection_id}@test-sync.example",
            created_at=now,
            updated_at=now,
            source_provider=MagicMock(provider="google_drive"),
        )

    active = _connection("active", 1)
    revoked = _connection("revoked", 2)
    sync_service._sync_repo.list_connections = AsyncMock(return_value=[revoked, active])

    result = await sync_service.list_connections(owner_id=7)

    assert len(result) == 1
    assert result[0].status == "active"


@pytest.mark.asyncio
async def test_get_connector_requires_collection_read(sync_service: DocumentSyncService):
    sync_service._collection_service.require_collection_access = AsyncMock()
    sync_service._sync_repo.get_connector_by_collection = AsyncMock(return_value=None)

    result = await sync_service.get_connector(
        collection_id=20,
        actor=ActorContext(tenant_id=1, user_id=7, user_role="viewer"),
    )

    assert result is None
    sync_service._collection_service.require_collection_access.assert_awaited_once_with(
        collection_id=20,
        actor=ActorContext(tenant_id=1, user_id=7, user_role="viewer"),
        action=ABAC_ACTION_READ,
    )


@pytest.mark.asyncio
async def test_delete_connector_requires_connection_owner(sync_service: DocumentSyncService):
    sync_service._collection_service.require_collection_access = AsyncMock()
    sync_service._sync_repo.get_connector_by_collection = AsyncMock(
        return_value=MagicMock(
            source_connection=MagicMock(owner_id=5),
        )
    )
    sync_service._sync_repo.stop_connector = AsyncMock()

    with pytest.raises(AuthorizationError):
        await sync_service.delete_connector(
            collection_id=20,
            actor=ActorContext(tenant_id=1, user_id=7, user_role="member"),
        )


@pytest.mark.asyncio
async def test_sync_connector_requires_connection_owner(sync_service: DocumentSyncService):
    connector = MagicMock(
        id=3,
        collection_id=20,
        status="active",
        source_connection=MagicMock(owner_id=5),
    )
    sync_service._sync_repo.acquire_connector_sync_lock = AsyncMock(return_value=connector)
    sync_service._collection_service.require_collection_access = AsyncMock()

    with pytest.raises(AuthorizationError):
        await sync_service.sync_connector(
            connector_id=3,
            actor=ActorContext(tenant_id=1, user_id=7, user_role="member"),
        )


@pytest.mark.asyncio
async def test_apply_sync_diff_revives_deleted_file_with_unchanged_timestamp(sync_service: DocumentSyncService):
    modified_at = datetime(2026, 1, 1, tzinfo=UTC)
    mapping = MagicMock(
        external_file_id="file-a",
        document_id=42,
        external_modified_at=modified_at,
    )
    sync_service._sync_repo.list_external_files = AsyncMock(return_value=[mapping])
    sync_service._document_is_deleted = AsyncMock(return_value=True)
    sync_service._update_existing_document = AsyncMock(return_value=True)
    sync_service._sync_repo.update_external_file = AsyncMock()

    result = await sync_service._apply_sync_diff(
        connector=MagicMock(id=5, collection_id=20),
        connection=MagicMock(owner_id=7),
        drive_client=AsyncMock(),
        remote_files=[_entry("file-a", modified_at=modified_at)],
    )

    assert result == SyncDiffResult(added=0, updated=1, deleted=0, skipped=0)
    sync_service._update_existing_document.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_connector_rejects_when_already_in_progress(sync_service: DocumentSyncService):
    sync_service._sync_repo.acquire_connector_sync_lock = AsyncMock(return_value=None)

    with pytest.raises(ValidationError) as exc_info:
        await sync_service.sync_connector(connector_id=5)

    assert exc_info.value.details.get("code") == "SYNC_IN_PROGRESS"


@pytest.mark.asyncio
async def test_sync_connector_skips_when_locked_and_skip_if_locked(sync_service: DocumentSyncService):
    sync_service._sync_repo.acquire_connector_sync_lock = AsyncMock(return_value=None)

    result = await sync_service.sync_connector(connector_id=5, skip_if_locked=True)

    assert result is None


@pytest.mark.asyncio
async def test_resolve_access_token_refreshes_when_expired(sync_service: DocumentSyncService):
    provider = MagicMock(id=5, enabled=True, provider="google_drive")
    connection = MagicMock(
        provider_id=5,
        source_provider=provider,
        oauth_credentials_enc={"enc": True},
    )
    expired = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    sync_service._provider_repo.get_provider_by_id = AsyncMock(return_value=provider)
    sync_service._provider_repo.decrypt_config = MagicMock(
        return_value={"client_id": "cid", "client_secret": "secret"},
    )
    sync_service._sync_repo.decrypt_credentials = MagicMock(
        return_value={
            "access_token": "old",
            "refresh_token": "refresh",
            "expires_at": expired,
        }
    )
    sync_service._sync_repo.encrypt_credentials = MagicMock(return_value={"enc": "updated"})
    sync_service.db_session = AsyncMock()

    with patch(
        "apps.shared.document.sync_service.GoogleDriveClient.refresh_access_token",
        new=AsyncMock(return_value={"access_token": "new-access", "expires_in": 3600}),
    ):
        token = await sync_service._resolve_access_token(connection)

    assert token == "new-access"
    assert connection.oauth_credentials_enc == {"enc": "updated"}


@pytest.mark.asyncio
async def test_update_existing_document_saves_under_doc_original_path(sync_service: DocumentSyncService):
    document_db = MagicMock()
    document_db.file_hash = "old-hash"
    document_db.filename = "old.pdf"
    document_db.file_url = "8/original/old.pdf"
    sync_service._document_repo.get_by_id_and_tenant = AsyncMock(return_value=document_db)
    sync_service._document_repo.update_document_file = AsyncMock()

    drive_client = AsyncMock()
    drive_client.download_file = AsyncMock(return_value=("report.pdf", b"new-content"))

    sync_service.file_storage.save = AsyncMock(return_value="8/original/report.pdf")
    sync_service.file_storage.get_size = AsyncMock(return_value=12)
    sync_service.file_storage.delete = AsyncMock(return_value=True)

    parse_pipeline = MagicMock()
    parse_pipeline.queue_document_reparse = AsyncMock()

    updated = await sync_service._update_existing_document(
        parse_pipeline=parse_pipeline,
        document_id=8,
        drive_client=drive_client,
        remote=_entry("file-a"),
    )

    assert updated is True
    sync_service.file_storage.save.assert_awaited_once_with("1", "8/original/report.pdf", ANY)
    sync_service._document_repo.update_document_file.assert_awaited_once()
    update_kwargs = sync_service._document_repo.update_document_file.await_args.kwargs
    assert update_kwargs["file_url"] == "8/original/report.pdf"
    sync_service.file_storage.delete.assert_awaited_once()
    parse_pipeline.queue_document_reparse.assert_awaited_once_with(8, triggered_by="drive_sync")
