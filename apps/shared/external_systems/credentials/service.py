"""Application use cases for user integration credentials."""

from __future__ import annotations

from sqlalchemy import select

from apps.shared.core.exceptions import IntegrationNotConnectedError, ResourceNotFoundError
from apps.shared.db.models import ApiConnector, DataSource
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.credentials.dtos import (
    UserIntegrationConnectionResponse,
    UserIntegrationConnectionTestResponse,
    UserIntegrationConnectionUpsertRequest,
)
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.external_systems.credentials.resolver import IntegrationCredentialResolver
from apps.shared.external_systems.credentials.user_integration_auth import validate_user_integration_upsert
from apps.shared.external_systems.domain.types import (
    CREDENTIAL_MODE_USER,
    USER_CONNECTION_CONNECTED,
    USER_CONNECTION_NOT_CONNECTED,
    IntegrationPurpose,
)
from apps.shared.utils.field_cipher import SENSITIVE_FIELD_KEYS, FieldCipher
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


class UserIntegrationCredentialService:
    def __init__(self, db_session, cipher: FieldCipher | None = None):
        self.db_session = db_session
        self.cipher = cipher or FieldCipher()
        self.repo = UserIntegrationCredentialRepository(db_session)
        self.resolver = IntegrationCredentialResolver(db_session, cipher=self.cipher)

    async def get_my_connection_data_source(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
    ) -> UserIntegrationConnectionResponse:
        ds = await self._get_data_source(actor.tenant_id, data_source_id)
        return await self._status_response(
            actor=actor,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=ds.id,
            credential_mode=getattr(ds, "credential_mode", None) or "shared",
        )

    async def get_my_connection_api_connector(
        self,
        *,
        actor: ActorContext,
        connector_id: int,
    ) -> UserIntegrationConnectionResponse:
        conn = await self._get_api_connector(actor.tenant_id, connector_id)
        return await self._status_response(
            actor=actor,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=conn.id,
            credential_mode=getattr(conn, "credential_mode", None) or "shared",
        )

    async def upsert_data_source_connection(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
        body: UserIntegrationConnectionUpsertRequest,
    ) -> UserIntegrationConnectionResponse:
        ds = await self._get_data_source(actor.tenant_id, data_source_id)
        self._require_user_mode(ds.credential_mode, RESOURCE_TYPE_DATA_SOURCE)
        merged_secrets = await self._merge_upsert_secrets(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=ds.id,
            incoming=body.secrets,
        )
        validate_user_integration_upsert(
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            auth_type=body.auth_type,
            merged_secrets=merged_secrets,
            data_source_type=ds.type,
        )
        secrets_enc = self.cipher.encrypt_dict(merged_secrets, sensitive_fields=SENSITIVE_FIELD_KEYS)
        await self.repo.upsert_binding(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=ds.id,
            auth_type=body.auth_type,
            secrets_enc=secrets_enc,
            account_label=body.account_label,
        )
        return await self._status_response(
            actor=actor,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=ds.id,
            credential_mode=CREDENTIAL_MODE_USER,
        )

    async def upsert_api_connector_connection(
        self,
        *,
        actor: ActorContext,
        connector_id: int,
        body: UserIntegrationConnectionUpsertRequest,
    ) -> UserIntegrationConnectionResponse:
        conn = await self._get_api_connector(actor.tenant_id, connector_id)
        self._require_user_mode(conn.credential_mode, RESOURCE_TYPE_API_CONNECTOR)
        merged_secrets = await self._merge_upsert_secrets(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=conn.id,
            incoming=body.secrets,
        )
        validate_user_integration_upsert(
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            auth_type=body.auth_type,
            merged_secrets=merged_secrets,
            connector_auth_type=conn.auth_type,
        )
        secrets_enc = self.cipher.encrypt_dict(merged_secrets, sensitive_fields=SENSITIVE_FIELD_KEYS)
        await self.repo.upsert_binding(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=conn.id,
            auth_type=body.auth_type,
            secrets_enc=secrets_enc,
            account_label=body.account_label,
        )
        return await self._status_response(
            actor=actor,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=conn.id,
            credential_mode=CREDENTIAL_MODE_USER,
        )

    async def disconnect_data_source(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
    ) -> None:
        ds = await self._get_data_source(actor.tenant_id, data_source_id)
        self._require_user_mode(ds.credential_mode, RESOURCE_TYPE_DATA_SOURCE)
        await self.repo.delete_binding(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=ds.id,
        )

    async def disconnect_api_connector(
        self,
        *,
        actor: ActorContext,
        connector_id: int,
    ) -> None:
        conn = await self._get_api_connector(actor.tenant_id, connector_id)
        self._require_user_mode(conn.credential_mode, RESOURCE_TYPE_API_CONNECTOR)
        await self.repo.delete_binding(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=conn.id,
        )

    async def test_data_source_connection(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
        body: UserIntegrationConnectionUpsertRequest | None = None,
    ) -> UserIntegrationConnectionTestResponse:
        from copy import deepcopy

        from apps.shared.utils.field_cipher import strip_sensitive_fields

        ds = await self._get_data_source(actor.tenant_id, data_source_id)
        self._require_user_mode(ds.credential_mode, RESOURCE_TYPE_DATA_SOURCE)
        if body is not None:
            merged_secrets = await self._merge_upsert_secrets(
                tenant_id=actor.tenant_id,
                user_id=actor.user_id,
                resource_type=RESOURCE_TYPE_DATA_SOURCE,
                resource_id=ds.id,
                incoming=body.secrets,
            )
            validate_user_integration_upsert(
                resource_type=RESOURCE_TYPE_DATA_SOURCE,
                auth_type=body.auth_type,
                merged_secrets=merged_secrets,
                data_source_type=ds.type,
            )
            resolved_config = {**strip_sensitive_fields(deepcopy(ds.config or {})), **merged_secrets}
        else:
            status, _ = await self.resolver.connection_status_for_actor(
                tenant_id=actor.tenant_id,
                user_id=actor.user_id,
                resource_type=RESOURCE_TYPE_DATA_SOURCE,
                resource_id=ds.id,
            )
            if status != USER_CONNECTION_CONNECTED:
                raise IntegrationNotConnectedError(
                    "Connect your account before testing",
                    {"code": "INTEGRATION_NOT_CONNECTED"},
                )
            resolved_config = await self.resolver.resolve_data_source_config(
                data_source=ds,
                actor=actor,
                purpose=IntegrationPurpose.QUERY,
            )
        from apps.shared.external_systems.data_source.adapters import db_data_source_to_domain_with_connection

        domain = db_data_source_to_domain_with_connection(ds, resolved_config)
        from apps.shared.infra.analytics_db.manager_factory import get_db_manager_for_datasource

        try:
            async with get_db_manager_for_datasource(domain) as manager:
                success, message = await manager.test_connection()
        except Exception as exc:
            logger.error("User data source connection test failed: %s", exc, exc_info=True)
            return UserIntegrationConnectionTestResponse(
                success=False,
                message="Connection test failed",
            )
        return UserIntegrationConnectionTestResponse(success=success, message=message)

    async def test_api_connector_connection(
        self,
        *,
        actor: ActorContext,
        connector_id: int,
        body: UserIntegrationConnectionUpsertRequest | None = None,
    ) -> UserIntegrationConnectionTestResponse:
        from copy import deepcopy

        from apps.shared.utils.field_cipher import strip_sensitive_fields

        conn = await self._get_api_connector(actor.tenant_id, connector_id)
        self._require_user_mode(conn.credential_mode, RESOURCE_TYPE_API_CONNECTOR)
        try:
            if body is not None:
                merged_secrets = await self._merge_upsert_secrets(
                    tenant_id=actor.tenant_id,
                    user_id=actor.user_id,
                    resource_type=RESOURCE_TYPE_API_CONNECTOR,
                    resource_id=conn.id,
                    incoming=body.secrets,
                )
                validate_user_integration_upsert(
                    resource_type=RESOURCE_TYPE_API_CONNECTOR,
                    auth_type=body.auth_type,
                    merged_secrets=merged_secrets,
                    connector_auth_type=conn.auth_type,
                )
                template = strip_sensitive_fields(deepcopy(conn.auth_config or {}))
                auth_dict = {**template, **merged_secrets}
                if not any(_non_empty_str(auth_dict.get(k)) for k in SENSITIVE_FIELD_KEYS if k in auth_dict):
                    return UserIntegrationConnectionTestResponse(
                        success=False,
                        message="Enter your credentials before testing",
                    )
            else:
                status, _ = await self.resolver.connection_status_for_actor(
                    tenant_id=actor.tenant_id,
                    user_id=actor.user_id,
                    resource_type=RESOURCE_TYPE_API_CONNECTOR,
                    resource_id=conn.id,
                )
                if status != USER_CONNECTION_CONNECTED:
                    raise IntegrationNotConnectedError(
                        "Connect your account before testing",
                        {"code": "INTEGRATION_NOT_CONNECTED"},
                    )
                auth_dict = await self.resolver.resolve_api_connector_auth_config(
                    connector=conn,
                    actor=actor,
                    purpose=IntegrationPurpose.EXECUTE,
                )
            if not auth_dict:
                return UserIntegrationConnectionTestResponse(
                    success=False,
                    message="Connection test failed",
                )
        except IntegrationNotConnectedError:
            raise
        except Exception as exc:
            logger.error("User API connector credential test failed: %s", exc, exc_info=True)
            return UserIntegrationConnectionTestResponse(
                success=False,
                message="Connection test failed",
            )
        return UserIntegrationConnectionTestResponse(success=True, message="Credentials validated successfully")

    async def _status_response(
        self,
        *,
        actor: ActorContext,
        resource_type: str,
        resource_id: int,
        credential_mode: str,
    ) -> UserIntegrationConnectionResponse:
        if credential_mode != CREDENTIAL_MODE_USER:
            return UserIntegrationConnectionResponse(
                resource_type=resource_type,
                resource_id=resource_id,
                status=USER_CONNECTION_NOT_CONNECTED,
            )
        status, row = await self.resolver.connection_status_for_actor(
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        secrets_public: dict[str, str] = {}
        secret_keys_configured: list[str] = []
        if row is not None and row.secrets_enc:
            decrypted = self.cipher.decrypt_dict(row.secrets_enc, sensitive_fields=SENSITIVE_FIELD_KEYS)
            secrets_public, secret_keys_configured = self._public_secrets_view(decrypted)
        return UserIntegrationConnectionResponse(
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            account_label=row.account_label if row else None,
            auth_type=row.auth_type if row else None,
            expires_at=row.expires_at if row else None,
            secrets_public=secrets_public,
            secret_keys_configured=secret_keys_configured,
        )

    async def _get_data_source(self, tenant_id: int, data_source_id: int) -> DataSource:
        result = await self.db_session.execute(
            select(DataSource).where(
                DataSource.tenant_id == tenant_id,
                DataSource.id == data_source_id,
            )
        )
        ds = result.scalar_one_or_none()
        if ds is None:
            raise ResourceNotFoundError(f"Data source {data_source_id} not found")
        return ds

    async def _get_api_connector(self, tenant_id: int, connector_id: int) -> ApiConnector:
        result = await self.db_session.execute(
            select(ApiConnector).where(
                ApiConnector.tenant_id == tenant_id,
                ApiConnector.id == connector_id,
            )
        )
        conn = result.scalar_one_or_none()
        if conn is None:
            raise ResourceNotFoundError(f"API connector {connector_id} not found")
        return conn


    async def _merge_upsert_secrets(
        self,
        *,
        tenant_id: int,
        user_id: int,
        resource_type: str,
        resource_id: int,
        incoming: dict[str, str],
    ) -> dict[str, str]:
        row = await self.repo.get_binding(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        existing: dict[str, str] = {}
        if row is not None and row.secrets_enc:
            decrypted = self.cipher.decrypt_dict(row.secrets_enc, sensitive_fields=SENSITIVE_FIELD_KEYS)
            existing = {k: v for k, v in decrypted.items() if isinstance(v, str)}
        merged = {**existing, **incoming}
        for key in SENSITIVE_FIELD_KEYS:
            if key not in incoming:
                continue
            if not _non_empty_str(incoming.get(key)):
                if _non_empty_str(existing.get(key)):
                    merged[key] = existing[key]
                else:
                    merged.pop(key, None)
        return merged

    @staticmethod
    def _public_secrets_view(decrypted: dict) -> tuple[dict[str, str], list[str]]:
        secrets_public: dict[str, str] = {}
        secret_keys_configured: list[str] = []
        for key, value in decrypted.items():
            if not isinstance(value, str) or not value.strip():
                continue
            if key in SENSITIVE_FIELD_KEYS:
                secret_keys_configured.append(key)
            else:
                secrets_public[key] = value
        secret_keys_configured.sort()
        return secrets_public, secret_keys_configured

    @staticmethod
    def _require_user_mode(credential_mode: str | None, resource_type: str) -> None:
        if (credential_mode or "shared") != CREDENTIAL_MODE_USER:
            raise ResourceNotFoundError(f"{resource_type} is not configured for per-user credentials")
