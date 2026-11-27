"""Application use cases for user integration credentials."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from apps.shared.core.exceptions import IntegrationNotConnectedError, ResourceNotFoundError
from apps.shared.db.models import ApiConnector, DataSource, User
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR, RESOURCE_TYPE_DATA_SOURCE
from apps.shared.external_systems.credentials.adapters import redact_user_integration_secrets_for_api
from apps.shared.external_systems.credentials.dtos import (
    UserIntegrationConnectionResponse,
    UserIntegrationConnectionSummary,
    UserIntegrationConnectionSummaryListResponse,
    UserIntegrationConnectionTestResponse,
    UserIntegrationConnectionUpsertRequest,
)
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.external_systems.credentials.resolver import IntegrationCredentialResolver
from apps.shared.external_systems.credentials.user_integration_auth import validate_user_integration_upsert
from apps.shared.external_systems.credentials.user_secrets_policy import (
    USER_BINDING_POLICY,
    prepare_user_binding_secrets_for_storage,
)
from apps.shared.external_systems.data_source.catalog_sync import strip_user_mode_connection_template
from apps.shared.external_systems.domain.types import (
    CREDENTIAL_MODE_USER,
    USER_CONNECTION_CONNECTED,
    USER_CONNECTION_NOT_CONNECTED,
    IntegrationPurpose,
)
from apps.shared.tenant.membership_repository import TenantMembershipRepository
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _actor_for_binding(actor: ActorContext, binding_user_id: int) -> ActorContext:
    return ActorContext(
        tenant_id=actor.tenant_id,
        user_id=binding_user_id,
        user_role=actor.user_role,
    )


class UserIntegrationCredentialService:
    def __init__(self, db_session, cipher: FieldCipher | None = None):
        self.db_session = db_session
        self.cipher = cipher or FieldCipher()
        self.repo = UserIntegrationCredentialRepository(db_session)
        self.membership_repo = TenantMembershipRepository(db_session)
        self.resolver = IntegrationCredentialResolver(db_session, cipher=self.cipher)

    async def _require_active_tenant_member(self, *, tenant_id: int, user_id: int) -> User:
        user = await self.membership_repo.get_active_member_user(tenant_id=tenant_id, user_id=user_id)
        if user is None:
            raise ResourceNotFoundError(f"User {user_id} not found")
        return user

    async def get_my_connection_data_source(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
    ) -> UserIntegrationConnectionResponse:
        return await self.get_user_connection_data_source(
            actor=actor,
            binding_user_id=actor.user_id,
            data_source_id=data_source_id,
        )

    async def get_my_connection_api_connector(
        self,
        *,
        actor: ActorContext,
        connector_id: int,
    ) -> UserIntegrationConnectionResponse:
        return await self.get_user_connection_api_connector(
            actor=actor,
            binding_user_id=actor.user_id,
            connector_id=connector_id,
        )

    async def get_user_connection_data_source(
        self,
        *,
        actor: ActorContext,
        binding_user_id: int,
        data_source_id: int,
    ) -> UserIntegrationConnectionResponse:
        await self._require_active_tenant_member(tenant_id=actor.tenant_id, user_id=binding_user_id)
        ds = await self._get_data_source(actor.tenant_id, data_source_id)
        return await self._status_response(
            actor=actor,
            binding_user_id=binding_user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=ds.id,
            credential_mode=getattr(ds, "credential_mode", None) or "shared",
        )

    async def get_user_connection_api_connector(
        self,
        *,
        actor: ActorContext,
        binding_user_id: int,
        connector_id: int,
    ) -> UserIntegrationConnectionResponse:
        await self._require_active_tenant_member(tenant_id=actor.tenant_id, user_id=binding_user_id)
        conn = await self._get_api_connector(actor.tenant_id, connector_id)
        return await self._status_response(
            actor=actor,
            binding_user_id=binding_user_id,
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
        binding_user_id: int | None = None,
        provisioned_by_user_id: int | None = None,
    ) -> UserIntegrationConnectionResponse:
        binding_user_id = actor.user_id if binding_user_id is None else binding_user_id
        ds = await self._get_data_source(actor.tenant_id, data_source_id)
        self._require_user_mode(ds.credential_mode, RESOURCE_TYPE_DATA_SOURCE)
        merged_secrets = await self._merge_upsert_secrets(
            tenant_id=actor.tenant_id,
            user_id=binding_user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=ds.id,
            incoming=body.secrets,
        )
        from apps.shared.external_systems.data_source.user_oauth import (
            user_credential_auth_type_from_config,
        )

        validate_user_integration_upsert(
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            auth_type=body.auth_type,
            merged_secrets=merged_secrets,
            data_source_type=ds.type,
            user_credential_auth_type=user_credential_auth_type_from_config(ds.config),
        )
        secrets_enc = prepare_user_binding_secrets_for_storage(merged_secrets, cipher=self.cipher)
        now = datetime.now(UTC)
        provision_kwargs: dict = {}
        if provisioned_by_user_id is not None:
            provision_kwargs = {
                "provisioned_by_user_id": provisioned_by_user_id,
                "provisioned_at": now,
            }
        elif binding_user_id == actor.user_id:
            provision_kwargs = {
                "provisioned_by_user_id": None,
                "provisioned_at": None,
            }
        await self.repo.upsert_binding(
            tenant_id=actor.tenant_id,
            user_id=binding_user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=ds.id,
            auth_type=body.auth_type,
            secrets_enc=secrets_enc,
            account_label=body.account_label,
            expires_at=body.expires_at,
            **provision_kwargs,
        )
        return await self._status_response(
            actor=actor,
            binding_user_id=binding_user_id,
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
        binding_user_id: int | None = None,
        provisioned_by_user_id: int | None = None,
    ) -> UserIntegrationConnectionResponse:
        binding_user_id = actor.user_id if binding_user_id is None else binding_user_id
        conn = await self._get_api_connector(actor.tenant_id, connector_id)
        self._require_user_mode(conn.credential_mode, RESOURCE_TYPE_API_CONNECTOR)
        merged_secrets = await self._merge_upsert_secrets(
            tenant_id=actor.tenant_id,
            user_id=binding_user_id,
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
        secrets_enc = prepare_user_binding_secrets_for_storage(merged_secrets, cipher=self.cipher)
        now = datetime.now(UTC)
        provision_kwargs: dict = {}
        if provisioned_by_user_id is not None:
            provision_kwargs = {
                "provisioned_by_user_id": provisioned_by_user_id,
                "provisioned_at": now,
            }
        elif binding_user_id == actor.user_id:
            provision_kwargs = {
                "provisioned_by_user_id": None,
                "provisioned_at": None,
            }
        await self.repo.upsert_binding(
            tenant_id=actor.tenant_id,
            user_id=binding_user_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=conn.id,
            auth_type=body.auth_type,
            secrets_enc=secrets_enc,
            account_label=body.account_label,
            expires_at=body.expires_at,
            **provision_kwargs,
        )
        return await self._status_response(
            actor=actor,
            binding_user_id=binding_user_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=conn.id,
            credential_mode=CREDENTIAL_MODE_USER,
        )

    async def admin_upsert_data_source_connection(
        self,
        *,
        actor: ActorContext,
        target_user_id: int,
        data_source_id: int,
        body: UserIntegrationConnectionUpsertRequest,
    ) -> UserIntegrationConnectionResponse:
        await self._require_active_tenant_member(tenant_id=actor.tenant_id, user_id=target_user_id)
        logger.info(
            "Admin provisioned data source user connection",
            extra={
                "tenant_id": actor.tenant_id,
                "resource_id": data_source_id,
                "binding_user_id": target_user_id,
                "actor_user_id": actor.user_id,
            },
        )
        return await self.upsert_data_source_connection(
            actor=actor,
            data_source_id=data_source_id,
            body=body,
            binding_user_id=target_user_id,
            provisioned_by_user_id=actor.user_id,
        )

    async def admin_upsert_api_connector_connection(
        self,
        *,
        actor: ActorContext,
        target_user_id: int,
        connector_id: int,
        body: UserIntegrationConnectionUpsertRequest,
    ) -> UserIntegrationConnectionResponse:
        await self._require_active_tenant_member(tenant_id=actor.tenant_id, user_id=target_user_id)
        logger.info(
            "Admin provisioned API connector user connection",
            extra={
                "tenant_id": actor.tenant_id,
                "resource_id": connector_id,
                "binding_user_id": target_user_id,
                "actor_user_id": actor.user_id,
            },
        )
        return await self.upsert_api_connector_connection(
            actor=actor,
            connector_id=connector_id,
            body=body,
            binding_user_id=target_user_id,
            provisioned_by_user_id=actor.user_id,
        )

    async def disconnect_data_source(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
        binding_user_id: int | None = None,
    ) -> None:
        binding_user_id = actor.user_id if binding_user_id is None else binding_user_id
        ds = await self._get_data_source(actor.tenant_id, data_source_id)
        self._require_user_mode(ds.credential_mode, RESOURCE_TYPE_DATA_SOURCE)
        await self.repo.delete_binding(
            tenant_id=actor.tenant_id,
            user_id=binding_user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=ds.id,
        )

    async def disconnect_api_connector(
        self,
        *,
        actor: ActorContext,
        connector_id: int,
        binding_user_id: int | None = None,
    ) -> None:
        binding_user_id = actor.user_id if binding_user_id is None else binding_user_id
        conn = await self._get_api_connector(actor.tenant_id, connector_id)
        self._require_user_mode(conn.credential_mode, RESOURCE_TYPE_API_CONNECTOR)
        await self.repo.delete_binding(
            tenant_id=actor.tenant_id,
            user_id=binding_user_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=conn.id,
        )

    async def admin_disconnect_data_source(
        self,
        *,
        actor: ActorContext,
        target_user_id: int,
        data_source_id: int,
    ) -> None:
        await self._require_active_tenant_member(tenant_id=actor.tenant_id, user_id=target_user_id)
        logger.info(
            "Admin removed data source user connection",
            extra={
                "tenant_id": actor.tenant_id,
                "resource_id": data_source_id,
                "binding_user_id": target_user_id,
                "actor_user_id": actor.user_id,
            },
        )
        await self.disconnect_data_source(actor=actor, data_source_id=data_source_id, binding_user_id=target_user_id)

    async def admin_disconnect_api_connector(
        self,
        *,
        actor: ActorContext,
        target_user_id: int,
        connector_id: int,
    ) -> None:
        await self._require_active_tenant_member(tenant_id=actor.tenant_id, user_id=target_user_id)
        logger.info(
            "Admin removed API connector user connection",
            extra={
                "tenant_id": actor.tenant_id,
                "resource_id": connector_id,
                "binding_user_id": target_user_id,
                "actor_user_id": actor.user_id,
            },
        )
        await self.disconnect_api_connector(actor=actor, connector_id=connector_id, binding_user_id=target_user_id)

    async def test_data_source_connection(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
        body: UserIntegrationConnectionUpsertRequest | None = None,
        binding_user_id: int | None = None,
    ) -> UserIntegrationConnectionTestResponse:
        from copy import deepcopy

        binding_user_id = actor.user_id if binding_user_id is None else binding_user_id
        if binding_user_id != actor.user_id:
            await self._require_active_tenant_member(tenant_id=actor.tenant_id, user_id=binding_user_id)
        binding_actor = _actor_for_binding(actor, binding_user_id)
        ds = await self._get_data_source(actor.tenant_id, data_source_id)
        self._require_user_mode(ds.credential_mode, RESOURCE_TYPE_DATA_SOURCE)
        if body is not None:
            merged_secrets = await self._merge_upsert_secrets(
                tenant_id=actor.tenant_id,
                user_id=binding_user_id,
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
            resolved_config = {
                **strip_user_mode_connection_template(deepcopy(ds.config or {})),
                **merged_secrets,
            }
        else:
            status, _ = await self.resolver.connection_status_for_actor(
                tenant_id=actor.tenant_id,
                user_id=binding_user_id,
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
                actor=binding_actor,
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
        binding_user_id: int | None = None,
    ) -> UserIntegrationConnectionTestResponse:
        from copy import deepcopy

        binding_user_id = actor.user_id if binding_user_id is None else binding_user_id
        if binding_user_id != actor.user_id:
            await self._require_active_tenant_member(tenant_id=actor.tenant_id, user_id=binding_user_id)
        binding_actor = _actor_for_binding(actor, binding_user_id)
        conn = await self._get_api_connector(actor.tenant_id, connector_id)
        self._require_user_mode(conn.credential_mode, RESOURCE_TYPE_API_CONNECTOR)
        try:
            if body is not None:
                merged_secrets = await self._merge_upsert_secrets(
                    tenant_id=actor.tenant_id,
                    user_id=binding_user_id,
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
                from apps.shared.external_systems.byot_template_strip import strip_connector_auth_user_mode_template

                template = strip_connector_auth_user_mode_template(
                    deepcopy(conn.auth_config or {}),
                    auth_type=body.auth_type,
                )
                auth_dict = {**template, **merged_secrets}
                if not any(
                    _non_empty_str(auth_dict.get(k))
                    for k in USER_BINDING_POLICY.encrypt_leaves
                    if k in auth_dict
                ):
                    return UserIntegrationConnectionTestResponse(
                        success=False,
                        message="Enter your credentials before testing",
                    )
            else:
                status, _ = await self.resolver.connection_status_for_actor(
                    tenant_id=actor.tenant_id,
                    user_id=binding_user_id,
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
                    actor=binding_actor,
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

    async def list_data_source_connections(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
    ) -> UserIntegrationConnectionSummaryListResponse:
        ds = await self._get_data_source(actor.tenant_id, data_source_id)
        self._require_user_mode(ds.credential_mode, RESOURCE_TYPE_DATA_SOURCE)
        rows = await self.repo.list_bindings_for_resource(
            tenant_id=actor.tenant_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=ds.id,
        )
        items = [await self._summary_for_binding(actor, row, user, provisioner) for row, user, provisioner in rows]
        return UserIntegrationConnectionSummaryListResponse(items=items)

    async def list_api_connector_connections(
        self,
        *,
        actor: ActorContext,
        connector_id: int,
    ) -> UserIntegrationConnectionSummaryListResponse:
        conn = await self._get_api_connector(actor.tenant_id, connector_id)
        self._require_user_mode(conn.credential_mode, RESOURCE_TYPE_API_CONNECTOR)
        rows = await self.repo.list_bindings_for_resource(
            tenant_id=actor.tenant_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=conn.id,
        )
        items = [await self._summary_for_binding(actor, row, user, provisioner) for row, user, provisioner in rows]
        return UserIntegrationConnectionSummaryListResponse(items=items)

    async def _summary_for_binding(self, actor: ActorContext, row, user, provisioner) -> UserIntegrationConnectionSummary:
        status, _ = await self.resolver.connection_status_for_actor(
            tenant_id=actor.tenant_id,
            user_id=row.user_id,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
        )
        return UserIntegrationConnectionSummary(
            user_id=row.user_id,
            username=user.username,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            resource_name=None,
            status=status,
            account_label=row.account_label,
            auth_type=row.auth_type,
            updated_at=row.updated_at,
            provisioned_by_user_id=row.provisioned_by_user_id,
            provisioned_by_username=provisioner.username if provisioner else None,
            provisioned_at=row.provisioned_at,
        )


    async def _status_response(
        self,
        *,
        actor: ActorContext,
        binding_user_id: int,
        resource_type: str,
        resource_id: int,
        credential_mode: str,
    ) -> UserIntegrationConnectionResponse:
        if credential_mode != CREDENTIAL_MODE_USER:
            return UserIntegrationConnectionResponse(
                resource_type=resource_type,
                resource_id=resource_id,
                status=USER_CONNECTION_NOT_CONNECTED,
                masked_fields=[],
            )
        status, row = await self.resolver.connection_status_for_actor(
            tenant_id=actor.tenant_id,
            user_id=binding_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        secrets: dict[str, str] = {}
        masked_fields: list[str] = []
        if row is not None and row.secrets_enc:
            decrypted = self.cipher.decrypt_dict(row.secrets_enc, sensitive_fields=USER_BINDING_POLICY.encrypt_leaves)
            secrets, masked_fields = redact_user_integration_secrets_for_api(decrypted)
        return UserIntegrationConnectionResponse(
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            account_label=row.account_label if row else None,
            auth_type=row.auth_type if row else None,
            expires_at=row.expires_at if row else None,
            secrets=secrets,
            masked_fields=masked_fields,
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
            decrypted = self.cipher.decrypt_dict(row.secrets_enc, sensitive_fields=USER_BINDING_POLICY.encrypt_leaves)
            existing = {k: v for k, v in decrypted.items() if isinstance(v, str)}
        merged = {**existing, **incoming}
        for key in USER_BINDING_POLICY.encrypt_leaves:
            if key not in incoming:
                continue
            if not _non_empty_str(incoming.get(key)):
                if _non_empty_str(existing.get(key)):
                    merged[key] = existing[key]
                else:
                    merged.pop(key, None)
        return merged

    @staticmethod
    def _require_user_mode(credential_mode: str | None, resource_type: str) -> None:
        if (credential_mode or "shared") != CREDENTIAL_MODE_USER:
            raise ResourceNotFoundError(f"{resource_type} is not configured for per-user credentials")
