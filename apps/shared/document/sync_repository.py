"""Tenant-scoped repository for document sync tables."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from apps.shared.db.models import (
    DocumentExternalFile,
    DocumentSourceConnection,
    DocumentSourceOAuthState,
    DocumentSyncConnector,
)
from apps.shared.document.sync_types import SENSITIVE_CONNECTION_CREDENTIAL_FIELDS
from apps.shared.utils.field_cipher import FieldCipher

_SOURCE_CONNECTION_LOAD = (
    selectinload(DocumentSyncConnector.source_connection).selectinload(
        DocumentSourceConnection.source_provider
    ),
    selectinload(DocumentSyncConnector.source_connection).selectinload(DocumentSourceConnection.owner_user),
)


def merge_connection_credentials(existing: dict, update: dict) -> dict:
    """Merge OAuth token fields, preserving refresh_token when absent in update."""
    merged = dict(existing)
    for key, value in update.items():
        if key == "refresh_token" and not value:
            continue
        merged[key] = value
    return merged


class DocumentSyncRepository:
    """Repository for source connections, connectors, OAuth states, and external file mappings."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cipher = FieldCipher()

    # ---------- OAuth states ----------

    async def create_oauth_state(
        self,
        *,
        tenant_id: int,
        user_id: int,
        provider_id: int,
        state: str,
        code_verifier: str,
        ttl_seconds: int = 600,
    ) -> DocumentSourceOAuthState:
        row = DocumentSourceOAuthState(
            tenant_id=tenant_id,
            user_id=user_id,
            provider_id=provider_id,
            state=state,
            code_verifier=code_verifier,
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def consume_oauth_state(self, state: str) -> DocumentSourceOAuthState | None:
        """Atomically delete and return a non-expired OAuth state (one-time use)."""
        result = await self.db.execute(
            delete(DocumentSourceOAuthState)
            .where(
                DocumentSourceOAuthState.state == state,
                DocumentSourceOAuthState.expires_at > datetime.now(UTC),
            )
            .returning(DocumentSourceOAuthState)
            .execution_options(synchronize_session=False)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        await self.db.flush()
        return row

    async def purge_expired_oauth_states(self, tenant_id: int | None = None) -> int:
        stmt = delete(DocumentSourceOAuthState).where(
            DocumentSourceOAuthState.expires_at <= datetime.now(UTC),
        )
        if tenant_id is not None:
            stmt = stmt.where(DocumentSourceOAuthState.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        await self.db.flush()
        return int(result.rowcount or 0)

    # ---------- Connections ----------

    async def list_connections(self, tenant_id: int, owner_id: int | None = None) -> list[DocumentSourceConnection]:
        stmt = (
            select(DocumentSourceConnection)
            .where(DocumentSourceConnection.tenant_id == tenant_id)
            .options(selectinload(DocumentSourceConnection.source_provider))
        )
        if owner_id is not None:
            stmt = stmt.where(DocumentSourceConnection.owner_id == owner_id)
        stmt = stmt.order_by(DocumentSourceConnection.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_connection(self, tenant_id: int, connection_id: int) -> DocumentSourceConnection | None:
        result = await self.db.execute(
            select(DocumentSourceConnection)
            .where(
                DocumentSourceConnection.tenant_id == tenant_id,
                DocumentSourceConnection.id == connection_id,
            )
            .options(selectinload(DocumentSourceConnection.source_provider))
        )
        return result.scalar_one_or_none()

    async def get_connection_for_owner(
        self,
        tenant_id: int,
        owner_id: int,
        provider_id: int,
    ) -> DocumentSourceConnection | None:
        result = await self.db.execute(
            select(DocumentSourceConnection)
            .where(
                DocumentSourceConnection.tenant_id == tenant_id,
                DocumentSourceConnection.owner_id == owner_id,
                DocumentSourceConnection.provider_id == provider_id,
            )
            .options(selectinload(DocumentSourceConnection.source_provider))
        )
        return result.scalar_one_or_none()

    async def upsert_connection(
        self,
        *,
        tenant_id: int,
        owner_id: int,
        provider_id: int,
        account_email: str | None,
        credentials: dict,
        status: str = "active",
    ) -> DocumentSourceConnection:
        row = await self.get_connection_for_owner(tenant_id, owner_id, provider_id)
        if row is None:
            encrypted = self._cipher.encrypt_dict(
                credentials,
                sensitive_fields=SENSITIVE_CONNECTION_CREDENTIAL_FIELDS,
            )
            row = DocumentSourceConnection(
                tenant_id=tenant_id,
                owner_id=owner_id,
                provider_id=provider_id,
                account_email=account_email,
                oauth_credentials_enc=encrypted,
                status=status,
            )
            self.db.add(row)
        else:
            merged_credentials = merge_connection_credentials(self.decrypt_credentials(row), credentials)
            row.account_email = account_email
            row.oauth_credentials_enc = self._cipher.encrypt_dict(
                merged_credentials,
                sensitive_fields=SENSITIVE_CONNECTION_CREDENTIAL_FIELDS,
            )
            row.status = status
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def revoke_connection(self, connection: DocumentSourceConnection) -> DocumentSourceConnection:
        connection.status = "revoked"
        connection.oauth_credentials_enc = {}
        await self.db.flush()
        await self.db.refresh(connection)
        return connection

    async def revoke_connections_for_owner(self, tenant_id: int, owner_id: int) -> None:
        connections = await self.list_connections(tenant_id, owner_id=owner_id)
        for connection in connections:
            if connection.status == "revoked":
                continue
            await self.stop_connectors_for_connection(tenant_id, connection.id)
            await self.revoke_connection(connection)

    def decrypt_credentials(self, connection: DocumentSourceConnection) -> dict:
        return self._cipher.decrypt_dict(connection.oauth_credentials_enc or {})

    def encrypt_credentials(self, credentials: dict) -> dict:
        return self._cipher.encrypt_dict(credentials, sensitive_fields=SENSITIVE_CONNECTION_CREDENTIAL_FIELDS)

    # ---------- Connectors ----------

    async def get_connector(self, tenant_id: int, connector_id: int) -> DocumentSyncConnector | None:
        result = await self.db.execute(
            select(DocumentSyncConnector)
            .where(
                DocumentSyncConnector.tenant_id == tenant_id,
                DocumentSyncConnector.id == connector_id,
            )
            .options(
                selectinload(DocumentSyncConnector.source_connection).selectinload(
                    DocumentSourceConnection.source_provider
                )
            )
        )
        return result.scalar_one_or_none()

    async def acquire_connector_sync_lock(
        self,
        tenant_id: int,
        connector_id: int,
        *,
        skip_locked: bool,
    ) -> DocumentSyncConnector | None:
        """Lock connector row for sync. skip_locked=True skips busy rows; otherwise uses NOWAIT."""
        stmt = (
            select(DocumentSyncConnector)
            .where(
                DocumentSyncConnector.tenant_id == tenant_id,
                DocumentSyncConnector.id == connector_id,
            )
            .options(*_SOURCE_CONNECTION_LOAD)
            .with_for_update(skip_locked=skip_locked, nowait=not skip_locked)
        )
        try:
            result = await self.db.execute(stmt)
        except DBAPIError as exc:
            orig = getattr(exc, "orig", None)
            sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
            if not skip_locked and sqlstate == "55P03":
                return None
            raise
        return result.scalar_one_or_none()

    async def get_connector_by_collection(self, tenant_id: int, collection_id: int) -> DocumentSyncConnector | None:
        result = await self.db.execute(
            select(DocumentSyncConnector)
            .where(
                DocumentSyncConnector.tenant_id == tenant_id,
                DocumentSyncConnector.collection_id == collection_id,
            )
            .options(*_SOURCE_CONNECTION_LOAD)
        )
        return result.scalar_one_or_none()

    async def create_connector(
        self,
        *,
        tenant_id: int,
        source_connection_id: int,
        collection_id: int,
        source_folder_id: str,
        source_folder_name: str,
        include_subfolders: bool,
    ) -> DocumentSyncConnector:
        row = DocumentSyncConnector(
            tenant_id=tenant_id,
            source_connection_id=source_connection_id,
            collection_id=collection_id,
            source_folder_id=source_folder_id,
            source_folder_name=source_folder_name,
            include_subfolders=include_subfolders,
            status="active",
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def stop_connector(self, connector: DocumentSyncConnector) -> DocumentSyncConnector:
        connector.status = "stopped"
        await self.db.flush()
        await self.db.refresh(connector)
        return connector

    async def list_active_connectors(self, tenant_id: int | None = None) -> list[DocumentSyncConnector]:
        stmt = (
            select(DocumentSyncConnector)
            .where(DocumentSyncConnector.status == "active")
            .options(
                selectinload(DocumentSyncConnector.source_connection).selectinload(
                    DocumentSourceConnection.source_provider
                )
            )
        )
        if tenant_id is not None:
            stmt = stmt.where(DocumentSyncConnector.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def update_connector_sync_state(
        self,
        connector: DocumentSyncConnector,
        *,
        last_synced_at: datetime | None = None,
        last_sync_error: str | None = None,
    ) -> DocumentSyncConnector:
        if last_synced_at is not None:
            connector.last_synced_at = last_synced_at
        connector.last_sync_error = last_sync_error
        await self.db.flush()
        await self.db.refresh(connector)
        return connector

    async def stop_connectors_for_connection(self, tenant_id: int, source_connection_id: int) -> None:
        result = await self.db.execute(
            select(DocumentSyncConnector).where(
                DocumentSyncConnector.tenant_id == tenant_id,
                DocumentSyncConnector.source_connection_id == source_connection_id,
            )
        )
        for connector in result.scalars().all():
            connector.status = "stopped"
        await self.db.flush()

    # ---------- External file mappings ----------

    async def list_external_files(self, tenant_id: int, connector_id: int) -> list[DocumentExternalFile]:
        result = await self.db.execute(
            select(DocumentExternalFile).where(
                DocumentExternalFile.tenant_id == tenant_id,
                DocumentExternalFile.connector_id == connector_id,
            )
        )
        return list(result.scalars().all())

    async def get_external_file(
        self,
        tenant_id: int,
        connector_id: int,
        external_file_id: str,
    ) -> DocumentExternalFile | None:
        result = await self.db.execute(
            select(DocumentExternalFile).where(
                DocumentExternalFile.tenant_id == tenant_id,
                DocumentExternalFile.connector_id == connector_id,
                DocumentExternalFile.external_file_id == external_file_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_external_file(
        self,
        *,
        tenant_id: int,
        connector_id: int,
        document_id: int,
        external_file_id: str,
        external_name: str,
        external_modified_at: datetime | None,
    ) -> DocumentExternalFile:
        row = DocumentExternalFile(
            tenant_id=tenant_id,
            connector_id=connector_id,
            document_id=document_id,
            external_file_id=external_file_id,
            external_name=external_name,
            external_modified_at=external_modified_at,
        )
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def update_external_file(
        self,
        mapping: DocumentExternalFile,
        *,
        document_id: int | None = None,
        external_name: str | None = None,
        external_modified_at: datetime | None = None,
    ) -> DocumentExternalFile:
        if document_id is not None:
            mapping.document_id = document_id
        if external_name is not None:
            mapping.external_name = external_name
        if external_modified_at is not None:
            mapping.external_modified_at = external_modified_at
        await self.db.flush()
        await self.db.refresh(mapping)
        return mapping

    async def clear_external_file_document(self, mapping: DocumentExternalFile) -> DocumentExternalFile:
        mapping.document_id = None
        await self.db.flush()
        await self.db.refresh(mapping)
        return mapping

    async def list_drive_linked_document_ids(
        self,
        tenant_id: int,
        collection_id: int,
        *,
        document_ids: list[int] | None = None,
    ) -> set[int]:
        """Document IDs in a collection that are linked to a Drive sync connector.

        When ``document_ids`` is provided, only those IDs are checked (e.g. one list page).
        """
        links = await self.map_drive_external_file_ids(
            tenant_id,
            document_ids=document_ids,
            collection_id=collection_id,
        )
        return set(links)

    async def map_drive_external_file_ids(
        self,
        tenant_id: int,
        *,
        document_ids: list[int] | None = None,
        collection_id: int | None = None,
    ) -> dict[int, str]:
        """Map document IDs to Drive external file IDs, optionally scoped to a collection."""
        if document_ids is not None and not document_ids:
            return {}

        stmt = select(DocumentExternalFile.document_id, DocumentExternalFile.external_file_id).where(
            DocumentExternalFile.tenant_id == tenant_id,
            DocumentExternalFile.document_id.is_not(None),
        )
        if collection_id is not None:
            stmt = stmt.join(
                DocumentSyncConnector,
                DocumentExternalFile.connector_id == DocumentSyncConnector.id,
            ).where(DocumentSyncConnector.collection_id == collection_id)
        if document_ids is not None:
            stmt = stmt.where(DocumentExternalFile.document_id.in_(document_ids))

        result = await self.db.execute(stmt)
        return {
            document_id: external_file_id
            for document_id, external_file_id in result.all()
            if document_id is not None and external_file_id
        }
