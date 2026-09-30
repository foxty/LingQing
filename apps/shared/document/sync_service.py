"""Document sync service — Google Drive and future external sources."""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import get_settings
from apps.shared.auth.oauth_pkce import generate_pkce
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.db.models import DocumentSourceProvider
from apps.shared.document.collection_service import DocumentCollectionService
from apps.shared.document.intake import DocumentIntake, IntakeRequest
from apps.shared.document.manifest import document_original_relative_key
from apps.shared.document.parse_pipeline import DocumentParsePipeline
from apps.shared.document.repository import DBDocumentRepository
from apps.shared.document.source_provider_repository import DocumentSourceProviderRepository
from apps.shared.document.sync_domain import (
    GoogleDriveProviderConfig,
    provider_label,
    require_provider_enabled,
)
from apps.shared.document.sync_repository import DocumentSyncRepository
from apps.shared.document.sync_schemas import (
    CreateSyncConnectorRequest,
    DocumentSourceConnectionResponse,
    DriveAuthorizeResponse,
    DrivePickerConfigResponse,
    GoogleDriveSourceConfigRequest,
    GoogleDriveSourceConfigResponse,
    SyncConnectorResponse,
    SyncConnectorResultResponse,
)
from apps.shared.document.sync_types import DEFAULT_DOCUMENT_SOURCE_PROVIDER
from apps.shared.document.types import DocumentStatus
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ, AUTHZ_ACTION_MANAGE
from apps.shared.infra.external_files.google_drive import GoogleDriveClient
from apps.shared.infra.external_files.port import ExternalFileEntry
from apps.shared.infra.storage import FileStorage
from apps.shared.infra.storage.paths import normalize_storage_key, resolve_storage_ref
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

DRIVE_CALLBACK_PATH = "/document-sync/google/callback"


@dataclass
class SyncDiffResult:
    added: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0


class DocumentSyncService(TenantAwareService):
    """Orchestrate external document source OAuth, connectors, and sync runs."""

    def __init__(
        self,
        tenant_id: int,
        db_session: AsyncSession,
        file_storage: FileStorage,
    ):
        super().__init__(tenant_id, db_session=db_session)
        self.file_storage = file_storage
        self._provider_repo = DocumentSourceProviderRepository(db_session)
        self._sync_repo = DocumentSyncRepository(db_session)
        self._document_repo = DBDocumentRepository(db_session)
        self._collection_service = DocumentCollectionService(tenant_id, db_session)
        self.settings = get_settings()

    def _redirect_uri(self) -> str:
        origin = self.settings.TENANT_APP_API_ORIGIN.rstrip("/")
        return f"{origin}{DRIVE_CALLBACK_PATH}"

    async def _get_provider_row(self, provider_key: str = DEFAULT_DOCUMENT_SOURCE_PROVIDER) -> DocumentSourceProvider:
        provider = await self._provider_repo.get_provider(self.tenant_id, provider_key)
        if provider is None:
            raise ValidationError(
                f"{provider_label(provider_key)} source is not configured for this tenant",
                {"code": "SOURCE_NOT_CONFIGURED", "provider": provider_key},
            )
        return provider

    async def _require_provider_enabled(
        self,
        provider_key: str = DEFAULT_DOCUMENT_SOURCE_PROVIDER,
    ) -> tuple[DocumentSourceProvider, GoogleDriveProviderConfig]:
        provider = await self._get_provider_row(provider_key)
        require_provider_enabled(provider_key=provider.provider, enabled=provider.enabled)
        config = GoogleDriveProviderConfig.from_dict(self._provider_repo.decrypt_config(provider))
        config.require_configured(provider_key=provider.provider)
        return provider, config

    async def _require_provider_by_id(
        self, provider_id: int
    ) -> tuple[DocumentSourceProvider, GoogleDriveProviderConfig]:
        provider = await self._provider_repo.get_provider_by_id(self.tenant_id, provider_id)
        if provider is None:
            raise ResourceNotFoundError(
                "Document source provider not found",
                {"code": "SOURCE_PROVIDER_NOT_FOUND", "provider_id": provider_id},
            )
        require_provider_enabled(provider_key=provider.provider, enabled=provider.enabled)
        config = GoogleDriveProviderConfig.from_dict(self._provider_repo.decrypt_config(provider))
        config.require_configured(provider_key=provider.provider)
        return provider, config

    async def get_google_drive_source(self) -> GoogleDriveSourceConfigResponse:
        provider = await self._provider_repo.get_provider(self.tenant_id, DEFAULT_DOCUMENT_SOURCE_PROVIDER)
        if provider is None:
            return GoogleDriveSourceConfigResponse(enabled=False, client_id=None, client_secret_configured=False)
        config = GoogleDriveProviderConfig.from_dict(self._provider_repo.decrypt_config(provider))
        return GoogleDriveSourceConfigResponse(
            enabled=provider.enabled,
            client_id=config.client_id or None,
            client_secret_configured=config.is_configured,
        )

    async def upsert_google_drive_source(
        self, request: GoogleDriveSourceConfigRequest
    ) -> GoogleDriveSourceConfigResponse:
        existing = await self._provider_repo.get_provider(self.tenant_id, DEFAULT_DOCUMENT_SOURCE_PROVIDER)
        merged_config: dict
        if existing is None:
            if not request.client_secret:
                raise ValidationError("client_secret is required when creating Google Drive source config")
            merged_config = {
                "client_id": request.client_id.strip(),
                "client_secret": request.client_secret.strip(),
            }
        else:
            current = self._provider_repo.decrypt_config(existing)
            merged_config = self._provider_repo.merge_config_update(
                current,
                {
                    "client_id": request.client_id.strip(),
                    "client_secret": request.client_secret.strip(),
                },
            )
        await self._provider_repo.upsert_provider(
            tenant_id=self.tenant_id,
            provider=DEFAULT_DOCUMENT_SOURCE_PROVIDER,
            enabled=request.enabled,
            config=merged_config,
        )
        return await self.get_google_drive_source()

    async def start_google_authorize(self, *, user_id: int) -> DriveAuthorizeResponse:
        provider, config = await self._require_provider_enabled()
        state, code_verifier, code_challenge = generate_pkce()
        await self._sync_repo.create_oauth_state(
            tenant_id=self.tenant_id,
            user_id=user_id,
            provider_id=provider.id,
            state=state,
            code_verifier=code_verifier,
        )
        url = GoogleDriveClient.build_authorize_url(
            client_id=config.client_id,
            redirect_uri=self._redirect_uri(),
            state=state,
            code_challenge=code_challenge,
        )
        return DriveAuthorizeResponse(authorize_url=url)

    @classmethod
    async def handle_google_callback_unscoped(
        cls,
        db_session: AsyncSession,
        file_storage: FileStorage,
        *,
        state: str,
        code: str,
    ) -> tuple[int, int]:
        """Complete OAuth callback without authenticated tenant context."""
        sync_repo = DocumentSyncRepository(db_session)
        oauth_state = await sync_repo.consume_oauth_state(state)
        if oauth_state is None:
            raise AuthenticationError("Invalid or expired OAuth state", {"code": "SOURCE_OAUTH_STATE_INVALID"})

        service = cls(oauth_state.tenant_id, db_session, file_storage)
        return await service._complete_google_callback(oauth_state=oauth_state, code=code)

    async def _complete_google_callback(self, *, oauth_state, code: str) -> tuple[int, int]:
        provider, config = await self._require_provider_by_id(oauth_state.provider_id)

        async with httpx.AsyncClient(timeout=30.0) as http_client:
            token_response = await GoogleDriveClient.exchange_code(
                client_id=config.client_id,
                client_secret=config.client_secret,
                redirect_uri=self._redirect_uri(),
                code=code,
                code_verifier=oauth_state.code_verifier,
                http_client=http_client,
            )
            access_token = token_response.get("access_token")
            if not access_token:
                raise AuthenticationError(
                    f"{provider_label(provider.provider)} token response missing access_token",
                    {"code": "SOURCE_TOKEN_MISSING", "provider": provider.provider},
                )

            account_email: str | None = None
            async with GoogleDriveClient(access_token=access_token, http_client=http_client) as drive_client:
                account_email = await drive_client.get_account_email()

        expires_at: str | None = None
        expires_in = token_response.get("expires_in")
        if expires_in:
            expires_at = (datetime.now(UTC) + timedelta(seconds=int(expires_in))).isoformat()
        credentials = {
            "access_token": access_token,
            "refresh_token": token_response.get("refresh_token"),
            "expires_at": expires_at,
            "token_type": token_response.get("token_type"),
        }
        await self._sync_repo.upsert_connection(
            tenant_id=self.tenant_id,
            owner_id=oauth_state.user_id,
            provider_id=provider.id,
            account_email=account_email,
            credentials=credentials,
            status="active",
        )
        return self.tenant_id, oauth_state.user_id

    async def list_connections(self, *, owner_id: int) -> list[DocumentSourceConnectionResponse]:
        rows = await self._sync_repo.list_connections(self.tenant_id, owner_id=owner_id)
        return [self._connection_to_response(row) for row in rows if row.status == "active"]

    async def get_picker_config(self, *, connection_id: int, owner_id: int) -> DrivePickerConfigResponse:
        connection = await self._sync_repo.get_connection(self.tenant_id, connection_id)
        if connection is None or connection.status != "active":
            raise ResourceNotFoundError("Source connection not found or inactive")
        if connection.owner_id != owner_id:
            raise AuthorizationError("Cannot use another user's source connection")
        _provider, config = await self._require_provider_by_id(connection.provider_id)
        access_token = await self._resolve_access_token(connection)
        return DrivePickerConfigResponse(client_id=config.client_id, access_token=access_token, app_id=config.client_id)

    async def disconnect_connection(self, *, connection_id: int, owner_id: int) -> None:
        connection = await self._sync_repo.get_connection(self.tenant_id, connection_id)
        if connection is None:
            raise ResourceNotFoundError("Source connection not found")
        if connection.owner_id != owner_id:
            raise AuthorizationError("Cannot disconnect another user's source connection")
        await self._sync_repo.stop_connectors_for_connection(self.tenant_id, connection.id)
        await self._sync_repo.revoke_connection(connection)

    async def create_connector(
        self,
        *,
        collection_id: int,
        request: CreateSyncConnectorRequest,
        actor: ActorContext,
    ) -> SyncConnectorResponse:
        collection = await self._collection_service.require_collection_access(
            collection_id=collection_id,
            actor=actor,
            action=AUTHZ_ACTION_MANAGE,
        )
        if collection.owner_id != actor.user_id:
            raise AuthorizationError("Only the collection owner can configure Drive sync")
        existing = await self._sync_repo.get_connector_by_collection(self.tenant_id, collection_id)
        if existing is not None:
            raise DuplicateResourceError(
                "Collection already has a sync connector",
                {"code": "SYNC_CONNECTOR_EXISTS"},
            )
        connection = await self._sync_repo.get_connection(self.tenant_id, request.source_connection_id)
        if connection is None or connection.status != "active":
            raise ResourceNotFoundError("Source connection not found or inactive")
        if connection.owner_id != actor.user_id:
            raise AuthorizationError("Cannot bind another user's source connection")

        await self._sync_repo.create_connector(
            tenant_id=self.tenant_id,
            source_connection_id=connection.id,
            collection_id=collection_id,
            source_folder_id=request.source_folder_id,
            source_folder_name=request.source_folder_name,
            include_subfolders=request.include_subfolders,
        )
        connector = await self._sync_repo.get_connector_by_collection(self.tenant_id, collection_id)
        assert connector is not None
        return self._connector_to_response(connector)

    async def get_connector(self, *, collection_id: int, actor: ActorContext) -> SyncConnectorResponse | None:
        await self._collection_service.require_collection_access(
            collection_id=collection_id,
            actor=actor,
            action=ABAC_ACTION_READ,
        )
        connector = await self._sync_repo.get_connector_by_collection(self.tenant_id, collection_id)
        if connector is None:
            return None
        return self._connector_to_response(connector)

    async def delete_connector(self, *, collection_id: int, actor: ActorContext) -> None:
        await self._collection_service.require_collection_access(
            collection_id=collection_id,
            actor=actor,
            action=ABAC_ACTION_READ,
        )
        connector = await self._sync_repo.get_connector_by_collection(self.tenant_id, collection_id)
        if connector is None:
            raise ResourceNotFoundError("Sync connector not found")
        self._require_connector_connection_owner(connector, actor)
        await self._sync_repo.stop_connector(connector)

    async def sync_connector(
        self,
        *,
        connector_id: int,
        actor: ActorContext | None = None,
        skip_if_locked: bool = False,
    ) -> SyncConnectorResultResponse | None:
        connector = await self._sync_repo.acquire_connector_sync_lock(
            self.tenant_id,
            connector_id,
            skip_locked=skip_if_locked,
        )
        if connector is None:
            if skip_if_locked:
                logger.info(
                    "document_sync_skipped_locked tenant_id=%s connector_id=%s",
                    self.tenant_id,
                    connector_id,
                )
                return None
            raise ValidationError("Sync already in progress", {"code": "SYNC_IN_PROGRESS"})
        if connector.status != "active":
            raise ValidationError("Sync connector is not active", {"code": "SYNC_CONNECTOR_STOPPED"})
        if actor is not None:
            await self._collection_service.require_collection_access(
                collection_id=connector.collection_id,
                actor=actor,
                action=ABAC_ACTION_READ,
            )
            self._require_connector_connection_owner(connector, actor)

        try:
            diff = await self._run_connector_sync(connector)
            await self._sync_repo.update_connector_sync_state(
                connector,
                last_synced_at=datetime.now(UTC),
                last_sync_error=None,
            )
        except Exception as exc:
            logger.exception(
                "document_sync_failed tenant_id=%s connector_id=%s error=%s",
                self.tenant_id,
                connector_id,
                exc,
            )
            await self._sync_repo.update_connector_sync_state(
                connector,
                last_sync_error=str(exc),
            )
            raise

        return SyncConnectorResultResponse(
            connector_id=connector.id,
            added=diff.added,
            updated=diff.updated,
            deleted=diff.deleted,
            skipped=diff.skipped,
        )

    async def sync_all_active_connectors(self, *, skip_if_locked: bool = True) -> list[SyncConnectorResultResponse]:
        connectors = await self._sync_repo.list_active_connectors(self.tenant_id)
        results: list[SyncConnectorResultResponse] = []
        for connector in connectors:
            try:
                result = await self.sync_connector(connector_id=connector.id, skip_if_locked=skip_if_locked)
                if result is not None:
                    results.append(result)
            except Exception as exc:
                logger.warning(
                    "document_sync_worker_connector_failed tenant_id=%s connector_id=%s error=%s",
                    self.tenant_id,
                    connector.id,
                    exc,
                )
        return results

    async def deactivate_user_connections(self, *, owner_id: int) -> None:
        """Revoke source connections and stop connectors when a user is deactivated."""
        await self._sync_repo.revoke_connections_for_owner(self.tenant_id, owner_id)

    async def _run_connector_sync(self, connector) -> SyncDiffResult:
        connection = connector.source_connection
        if connection is None or connection.status != "active":
            raise ValidationError("Source connection is not active")

        access_token = await self._resolve_access_token(connection)
        async with GoogleDriveClient(access_token=access_token) as drive_client:
            remote_files = await drive_client.list_folder_tree(
                connector.source_folder_id,
                include_subfolders=connector.include_subfolders,
            )
            return await self._apply_sync_diff(
                connector=connector,
                connection=connection,
                drive_client=drive_client,
                remote_files=remote_files,
            )

    async def _resolve_access_token(self, connection) -> str:
        _provider, config = await self._require_provider_by_id(connection.provider_id)
        credentials = self._sync_repo.decrypt_credentials(connection)
        access_token = (credentials.get("access_token") or "").strip()
        refresh_token = (credentials.get("refresh_token") or "").strip()
        if access_token and not self._token_needs_refresh(credentials):
            return access_token
        if not refresh_token:
            provider_key = connection.source_provider.provider if connection.source_provider else "unknown"
            raise AuthenticationError(
                f"{provider_label(provider_key)} connection has no valid credentials",
                {"code": "SOURCE_AUTH_MISSING", "provider": provider_key},
            )
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            token_response = await GoogleDriveClient.refresh_access_token(
                client_id=config.client_id,
                client_secret=config.client_secret,
                refresh_token=refresh_token,
                http_client=http_client,
            )
        new_access = token_response.get("access_token")
        if not new_access:
            provider_key = connection.source_provider.provider if connection.source_provider else "unknown"
            raise AuthenticationError(
                f"{provider_label(provider_key)} token refresh did not return access_token",
                {"code": "SOURCE_TOKEN_REFRESH_FAILED", "provider": provider_key},
            )
        credentials["access_token"] = new_access
        if token_response.get("refresh_token"):
            credentials["refresh_token"] = token_response["refresh_token"]
        expires_in = token_response.get("expires_in")
        if expires_in:
            credentials["expires_at"] = (datetime.now(UTC) + timedelta(seconds=int(expires_in))).isoformat()
        connection.oauth_credentials_enc = self._sync_repo.encrypt_credentials(credentials)
        await self.db_session.flush()
        return new_access

    @staticmethod
    def _token_needs_refresh(credentials: dict) -> bool:
        expires_at_str = credentials.get("expires_at")
        if not expires_at_str:
            return False
        try:
            expires_at = datetime.fromisoformat(str(expires_at_str))
        except ValueError:
            return False
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return datetime.now(UTC) >= expires_at - timedelta(minutes=2)

    async def _apply_sync_diff(
        self,
        *,
        connector,
        connection,
        drive_client: GoogleDriveClient,
        remote_files: list[ExternalFileEntry],
    ) -> SyncDiffResult:
        result = SyncDiffResult()
        remote_by_id = {item.external_id: item for item in remote_files}
        mappings = await self._sync_repo.list_external_files(self.tenant_id, connector.id)
        mapping_by_external_id = {row.external_file_id: row for row in mappings}

        intake = DocumentIntake(self.tenant_id, self.db_session, self.file_storage)
        parse_pipeline = DocumentParsePipeline(self.tenant_id, self.db_session, self.file_storage)

        for external_id, remote in remote_by_id.items():
            mapping = mapping_by_external_id.get(external_id)
            if mapping is None:
                added_doc = await self._intake_remote_file(
                    intake=intake,
                    connector=connector,
                    connection=connection,
                    drive_client=drive_client,
                    remote=remote,
                )
                if added_doc is None:
                    result.skipped += 1
                    continue
                await self._sync_repo.create_external_file(
                    tenant_id=self.tenant_id,
                    connector_id=connector.id,
                    document_id=added_doc.id,
                    external_file_id=external_id,
                    external_name=remote.name,
                    external_modified_at=remote.modified_at,
                )
                logger.info(
                    "document_sync_added tenant_id=%s connector_id=%s external_file_id=%s document_id=%s",
                    self.tenant_id,
                    connector.id,
                    external_id,
                    added_doc.id,
                )
                result.added += 1
                continue

            needs_revive = await self._document_is_deleted(mapping.document_id)
            if self._is_unchanged(mapping.external_modified_at, remote.modified_at) and not needs_revive:
                logger.info(
                    "document_sync_skip_unchanged tenant_id=%s connector_id=%s external_file_id=%s document_id=%s",
                    self.tenant_id,
                    connector.id,
                    external_id,
                    mapping.document_id,
                )
                result.skipped += 1
                continue

            if mapping.document_id is None:
                added_doc = await self._intake_remote_file(
                    intake=intake,
                    connector=connector,
                    connection=connection,
                    drive_client=drive_client,
                    remote=remote,
                )
                if added_doc is None:
                    result.skipped += 1
                    continue
                await self._sync_repo.update_external_file(
                    mapping,
                    document_id=added_doc.id,
                    external_name=remote.name,
                    external_modified_at=remote.modified_at,
                )
                result.updated += 1
                continue

            if needs_revive:
                logger.info(
                    "document_sync_revive tenant_id=%s connector_id=%s external_file_id=%s document_id=%s",
                    self.tenant_id,
                    connector.id,
                    external_id,
                    mapping.document_id,
                )
                updated = await self._update_existing_document(
                    parse_pipeline=parse_pipeline,
                    document_id=mapping.document_id,
                    drive_client=drive_client,
                    remote=remote,
                    reason="revive",
                )
                await self._sync_repo.update_external_file(
                    mapping,
                    external_name=remote.name,
                    external_modified_at=remote.modified_at,
                )
                if updated:
                    result.updated += 1
                else:
                    result.skipped += 1
                continue

            updated = await self._update_existing_document(
                parse_pipeline=parse_pipeline,
                document_id=mapping.document_id,
                drive_client=drive_client,
                remote=remote,
                reason="modified",
            )
            await self._sync_repo.update_external_file(
                mapping,
                external_name=remote.name,
                external_modified_at=remote.modified_at,
            )
            if updated:
                result.updated += 1
            else:
                result.skipped += 1

        for external_id, mapping in mapping_by_external_id.items():
            if external_id in remote_by_id:
                continue
            if mapping.document_id is not None:
                if await self._document_repo.soft_delete(mapping.document_id, self.tenant_id):
                    await self._sync_repo.clear_external_file_document(mapping)
                    logger.info(
                        "document_sync_deleted tenant_id=%s connector_id=%s external_file_id=%s document_id=%s",
                        self.tenant_id,
                        connector.id,
                        external_id,
                        mapping.document_id,
                    )
                    result.deleted += 1

        logger.info(
            "document_sync_diff tenant_id=%s connector_id=%s added=%s updated=%s deleted=%s skipped=%s",
            self.tenant_id,
            connector.id,
            result.added,
            result.updated,
            result.deleted,
            result.skipped,
        )
        return result

    async def _intake_remote_file(
        self,
        *,
        intake: DocumentIntake,
        connector,
        connection,
        drive_client: GoogleDriveClient,
        remote: ExternalFileEntry,
    ):
        filename, content = await drive_client.download_file(remote)
        doc = await intake.persist(
            IntakeRequest(
                collection_id=connector.collection_id,
                filename=filename,
                content=content,
                owner_id=connection.owner_id,
                source="drive_sync",
                on_duplicate="skip",
            )
        )
        return doc

    async def _update_existing_document(
        self,
        *,
        parse_pipeline: DocumentParsePipeline,
        document_id: int,
        drive_client: GoogleDriveClient,
        remote: ExternalFileEntry,
        reason: str = "modified",
    ) -> bool:
        document_db = await self._document_repo.get_by_id_and_tenant(document_id, self.tenant_id)
        if document_db is None:
            logger.warning(
                "document_sync_update_missing_document tenant_id=%s document_id=%s external_file_id=%s",
                self.tenant_id,
                document_id,
                remote.external_id,
            )
            return False

        filename, content = await drive_client.download_file(remote)
        logger.info(
            "document_sync_download tenant_id=%s document_id=%s external_file_id=%s reason=%s bytes=%s",
            self.tenant_id,
            document_id,
            remote.external_id,
            reason,
            len(content),
        )
        file_hash = DocumentIntake.calculate_file_hash(content)
        if document_db.file_hash == file_hash and document_db.filename == filename:
            logger.info(
                "document_sync_skip_hash_match tenant_id=%s document_id=%s external_file_id=%s reason=%s",
                self.tenant_id,
                document_id,
                remote.external_id,
                reason,
            )
            return False

        old_file_url = document_db.file_url
        relative_key = document_original_relative_key(document_id, filename)
        storage_key = await self.file_storage.save(
            str(self.tenant_id),
            relative_key,
            io.BytesIO(content),
        )
        file_url = normalize_storage_key(self.tenant_id, storage_key)
        file_size = await self.file_storage.get_size(resolve_storage_ref(self.tenant_id, file_url))

        await self._document_repo.update_document_file(
            document_id,
            self.tenant_id,
            filename=filename,
            file_url=file_url,
            file_size=file_size,
            file_hash=file_hash,
        )

        if old_file_url != file_url:
            try:
                await self.file_storage.delete(resolve_storage_ref(self.tenant_id, old_file_url))
            except Exception as exc:
                logger.warning(
                    "document_sync_old_file_delete_failed tenant_id=%s document_id=%s error=%s",
                    self.tenant_id,
                    document_id,
                    exc,
                )

        logger.info(
            "document_sync_updated tenant_id=%s document_id=%s external_file_id=%s reason=%s "
            "old_file_url=%s new_file_url=%s",
            self.tenant_id,
            document_id,
            remote.external_id,
            reason,
            old_file_url,
            file_url,
        )
        await parse_pipeline.queue_document_reparse(document_id, triggered_by="drive_sync")
        return True

    async def _document_is_deleted(self, document_id: int | None) -> bool:
        if document_id is None:
            return False
        document = await self._document_repo.get_by_id_and_tenant(document_id, self.tenant_id)
        if document is None:
            return True
        return document.status == DocumentStatus.DELETED.value

    @staticmethod
    def _is_unchanged(existing_modified_at: datetime | None, remote_modified_at: datetime | None) -> bool:
        if existing_modified_at is None or remote_modified_at is None:
            return False
        return existing_modified_at == remote_modified_at

    @staticmethod
    def _connection_to_response(connection) -> DocumentSourceConnectionResponse:
        provider_key = connection.source_provider.provider if connection.source_provider else "unknown"
        return DocumentSourceConnectionResponse(
            id=connection.id,
            provider_id=connection.provider_id,
            provider=provider_key,
            account_email=connection.account_email,
            status=connection.status,
            created_at=connection.created_at,
            updated_at=connection.updated_at,
        )

    @staticmethod
    def _require_connector_connection_owner(connector, actor: ActorContext) -> None:
        connection = connector.source_connection
        if connection is None or connection.owner_id != actor.user_id:
            raise AuthorizationError("Cannot manage another user's source connection")

    @staticmethod
    def _connector_to_response(connector) -> SyncConnectorResponse:
        connection = connector.source_connection
        owner_user = connection.__dict__.get("owner_user") if connection is not None else None
        owner_username = owner_user.username if owner_user is not None else None
        return SyncConnectorResponse(
            id=connector.id,
            source_connection_id=connector.source_connection_id,
            collection_id=connector.collection_id,
            source_folder_id=connector.source_folder_id,
            source_folder_name=connector.source_folder_name,
            include_subfolders=connector.include_subfolders,
            status=connector.status,
            last_synced_at=connector.last_synced_at,
            last_sync_error=connector.last_sync_error,
            connection_owner_id=connection.owner_id if connection is not None else 0,
            connection_owner_username=owner_username,
            account_email=connection.account_email if connection is not None else None,
            created_at=connector.created_at,
            updated_at=connector.updated_at,
        )
