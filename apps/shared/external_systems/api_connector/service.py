"""Control plane: API connector and operation index lifecycle.

Covers CRUD, OpenAPI/schema sync, manual operations, ABAC-enriched list/detail,
and resource-index side effects. Pack install/sync and runtime HTTP execution
live elsewhere (``packs/``, ``execution.py``).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.authz_query_builder import (
    AuthzSqlFilter,
    build_unified_resource_filter,
    evaluate_resource_action,
)
from apps.shared.core.exceptions import (
    AuthorizationError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.core.transaction import transaction
from apps.shared.db.models import AclGrant, ApiConnector, ResourceAcl
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    ABAC_ACTION_WRITE,
    RESOURCE_TYPE_API_CONNECTOR,
)
from apps.shared.external_systems.api_connector.adapters import (
    apply_connector_pack_metadata_to_entity,
    apply_operation_domain_to_entity,
    auth_config_to_dict,
    connector_domain_to_response,
    connector_entity_to_domain,
    imported_operation_domain_from_spec,
    manual_operation_domain_from_values,
    new_connector_entity_from_create,
    operation_domain_to_new_entity,
    operation_entity_to_domain,
)
from apps.shared.external_systems.api_connector.constants import (
    ALLOWED_HTTP_METHODS,
    AUTH_REQUIREMENT_REQUIRED,
    AUTH_TYPE_OAUTH2,
    OPERATION_SOURCE_MANUAL,
    OPERATION_STATUS_ACTIVE,
    OPERATION_STATUS_DISABLED,
    OPERATION_STATUS_STALE,
    RISK_LEVEL_MEDIUM,
)
from apps.shared.external_systems.api_connector.domain import (
    ApiConnectorDomain,
    ApiOperationDomain,
    AuthConfig,
    AuthRequirement,
    AuthType,
    ConnectorStatus,
    ExecutionRulesDomain,
    OperationStatus,
    RatePolicyDomain,
    RiskLevel,
    SchemaSourceType,
)
from apps.shared.external_systems.api_connector.operation_catalog import ApiOperationResourceIndexWriter
from apps.shared.external_systems.api_connector.pack_operations import (
    apply_pack_manifest,
    install_integration_pack,
    sync_installed_pack_for_connector,
)
from apps.shared.external_systems.api_connector.repository import ApiConnectorRepository, ApiOperationIndexRepository
from apps.shared.external_systems.api_connector.schema_parser import OpenApiParser, OperationSpec, SchemaSourceResolver
from apps.shared.external_systems.api_connector.schemas import (
    ApiConnectorResponse,
    ApiOperationStatsResponse,
    InstallPackOAuthInput,
    PackSyncSummaryDTO,
    SyncSchemaSummaryDTO,
)
from apps.shared.external_systems.byot_template_strip import strip_connector_auth_user_mode_template
from apps.shared.external_systems.credentials.repository import UserIntegrationCredentialRepository
from apps.shared.external_systems.credentials.resolver import IntegrationCredentialResolver
from apps.shared.external_systems.domain.types import (
    CREDENTIAL_MODE_SHARED,
    CREDENTIAL_MODE_USER,
    CredentialModeStr,
    UserConnectionStatus,
    effective_credential_mode,
)
from apps.shared.external_systems.packs.catalog import IntegrationPackCatalog
from apps.shared.external_systems.packs.schemas import ApiConnectorPackManifest
from apps.shared.external_systems.packs.versioning import pack_update_metadata
from apps.shared.search.repository import ResourceIndexRepository
from apps.shared.tag.repository import TagBindingRepository
from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.logger import get_logger
from apps.shared.utils.pagination import PaginationRequest

logger = get_logger(__name__)


class ApiConnectorService:
    """Control-plane use cases for connectors and indexed operations (desired state)."""

    def __init__(self, tenant_id: int, db_session: AsyncSession):
        self.tenant_id = tenant_id
        self.db_session = db_session
        self.connector_repo = ApiConnectorRepository(db_session)
        self.operation_repo = ApiOperationIndexRepository(db_session)
        self.cipher = FieldCipher()
        self._operation_index_writer = ApiOperationResourceIndexWriter(
            tenant_id=tenant_id,
            db_session=db_session,
        )
        self._resource_index_repo: ResourceIndexRepository | None = None

    def _get_resource_index_repo(self) -> ResourceIndexRepository:
        """Lazy-initialize ResourceIndexRepository."""
        if self._resource_index_repo is None:
            self._resource_index_repo = ResourceIndexRepository(self.db_session)
        return self._resource_index_repo

    async def create_connector(
        self,
        *,
        owner_id: int,
        name: str,
        description: str | None,
        base_url: str,
        auth_type: AuthType,
        auth_config: AuthConfig | dict[str, Any],
        rate_policy: RatePolicyDomain | None,
        schema_source_type: SchemaSourceType,
        schema_source_url: str | None,
        credential_mode: CredentialModeStr = CREDENTIAL_MODE_SHARED,
        execution_rules: ExecutionRulesDomain | None = None,
        pack_ref: str | None = None,
        installed_pack_version: str | None = None,
        agent_instructions: str | None = None,
    ) -> ApiConnectorResponse:
        existing = await self.connector_repo.get_by_tenant_and_name(self.tenant_id, name)
        if existing:
            raise DuplicateResourceError(f"API connector already exists: {name}")

        auth_config_dict = auth_config_to_dict(auth_config)
        self._validate_auth_config(auth_type, auth_config_dict, credential_mode=credential_mode)
        if credential_mode == CREDENTIAL_MODE_USER:
            auth_config_dict = strip_connector_auth_user_mode_template(auth_config_dict, auth_type=auth_type)

        from apps.shared.external_systems.api_connector.auth_config_secrets_policy import (
            prepare_auth_config_for_storage,
        )

        encrypted_auth = prepare_auth_config_for_storage(auth_config_dict, cipher=self.cipher)

        connector = new_connector_entity_from_create(
            tenant_id=self.tenant_id,
            owner_id=owner_id,
            name=name,
            description=description,
            base_url=base_url,
            auth_type=auth_type,
            auth_config_encrypted=encrypted_auth,
            rate_policy=self._to_rate_policy_dict(rate_policy),
            schema_source_type=schema_source_type,
            schema_source_url=schema_source_url,
            credential_mode=credential_mode,
            pack_ref=pack_ref,
            installed_pack_version=installed_pack_version,
            agent_instructions=agent_instructions,
            execution_rules=(execution_rules or ExecutionRulesDomain()).to_dict(),
        )
        created = await self.connector_repo.create(connector)
        created_with_owner = await self.connector_repo.get_by_id_and_tenant(created.id, self.tenant_id)
        return connector_domain_to_response(
            connector_entity_to_domain(created_with_owner or created, cipher=self.cipher)
        )

    async def _connector_rows_to_responses(self, rows: list[ApiConnector]) -> list[ApiConnectorResponse]:
        return [connector_domain_to_response(connector_entity_to_domain(row, cipher=self.cipher)) for row in rows]

    async def _enrich_connector_responses_for_actor(
        self,
        responses: list[ApiConnectorResponse],
        actor: ActorContext,
    ) -> list[ApiConnectorResponse]:
        """Attach actor-scoped capabilities (write) and user connection status."""
        if not responses:
            return responses
        resolver = IntegrationCredentialResolver(self.db_session)
        enriched: list[ApiConnectorResponse] = []
        for item in responses:
            can_write = await evaluate_resource_action(
                db_session=self.db_session,
                tenant_id=self.tenant_id,
                user_id=actor.user_id,
                user_role=actor.user_role,
                resource_type=RESOURCE_TYPE_API_CONNECTOR,
                resource_id=item.id,
                resource_owner_id=item.owner_id,
                action=ABAC_ACTION_WRITE,
            )
            updates: dict[str, object] = {"can_write": can_write}
            if item.credential_mode == CREDENTIAL_MODE_USER:
                status, _ = await resolver.connection_status_for_actor(
                    tenant_id=self.tenant_id,
                    user_id=actor.user_id,
                    resource_type=RESOURCE_TYPE_API_CONNECTOR,
                    resource_id=item.id,
                )
                updates["user_connection_status"] = UserConnectionStatus(status)
            catalog_version, pack_update_available = pack_update_metadata(
                pack_ref=item.pack_ref,
                installed_pack_version=item.installed_pack_version,
            )
            updates["pack_catalog_version"] = catalog_version
            updates["pack_update_available"] = pack_update_available
            enriched.append(item.model_copy(update=updates))
        return enriched

    async def _connector_abac_scope(self, *, actor: ActorContext) -> AuthzSqlFilter:
        return await build_unified_resource_filter(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            action=ABAC_ACTION_READ,
            resource_model=ApiConnector,
        )

    @staticmethod
    def _connector_row_matches_query(row: ApiConnector, query: str | None) -> bool:
        normalized_query = query.strip().lower() if query else None
        if not normalized_query:
            return True
        searchable = " ".join(part for part in (row.name, row.description, row.base_url) if part).lower()
        return normalized_query in searchable

    async def _readable_connector_rows_for_actor(
        self,
        *,
        actor: ActorContext,
        abac_scope: AuthzSqlFilter,
        query: str | None = None,
    ) -> list[ApiConnector]:
        if abac_scope.deny_all:
            return []

        scope_clause = None if abac_scope.allow_all else abac_scope.clause
        rows = await self.connector_repo.list_by_tenant(
            self.tenant_id,
            scope_clause=scope_clause,
        )
        if abac_scope.allow_all:
            return [row for row in rows if self._connector_row_matches_query(row, query)]

        allowed: list[ApiConnector] = []
        for row in rows:
            if not self._connector_row_matches_query(row, query):
                continue
            ok = await evaluate_resource_action(
                db_session=self.db_session,
                tenant_id=self.tenant_id,
                user_id=actor.user_id,
                user_role=actor.user_role,
                resource_type=RESOURCE_TYPE_API_CONNECTOR,
                resource_id=row.id,
                resource_owner_id=row.owner_id,
                action=ABAC_ACTION_READ,
            )
            if ok:
                allowed.append(row)
        return allowed

    async def _readable_connector_ids_for_actor(self, *, actor: ActorContext) -> list[int]:
        abac_scope = await self._connector_abac_scope(actor=actor)
        rows = await self._readable_connector_rows_for_actor(actor=actor, abac_scope=abac_scope)
        return [row.id for row in rows]

    async def list_connectors_paginated_for_actor(
        self,
        *,
        actor: ActorContext,
        page: int,
        page_size: int,
        query: str | None = None,
    ) -> tuple[list[ApiConnectorResponse], PaginationRequest]:
        abac_scope = await self._connector_abac_scope(actor=actor)
        if abac_scope.deny_all:
            return [], PaginationRequest.with_total(page=page, page_size=page_size, total=0)

        if abac_scope.allow_all:
            scope_clause = None
            total = await self.connector_repo.count_by_tenant_filtered(
                self.tenant_id,
                scope_clause=scope_clause,
                query=query,
            )
            pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=total)
            if total == 0:
                return [], pagination

            rows = await self.connector_repo.list_by_tenant_paginated(
                self.tenant_id,
                limit=pagination.page_size,
                offset=pagination.offset,
                scope_clause=scope_clause,
                query=query,
            )
            responses = await self._connector_rows_to_responses(rows)
            return await self._enrich_connector_responses_for_actor(responses, actor), pagination

        allowed_rows = await self._readable_connector_rows_for_actor(
            actor=actor,
            abac_scope=abac_scope,
            query=query,
        )
        total = len(allowed_rows)
        pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=total)
        if total == 0:
            return [], pagination

        page_rows = allowed_rows[pagination.offset : pagination.offset + pagination.page_size]
        responses = await self._connector_rows_to_responses(page_rows)
        return await self._enrich_connector_responses_for_actor(responses, actor), pagination

    async def get_connector_for_actor(self, *, connector_id: int, actor: ActorContext) -> ApiConnectorResponse:
        connector = await self.connector_repo.get_by_id_and_tenant(connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"ApiConnector not found: {connector_id}")

        allowed = await evaluate_resource_action(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            resource_owner_id=connector.owner_id,
            action=ABAC_ACTION_READ,
        )
        if not allowed:
            raise AuthorizationError("Access denied to API connector")
        response = connector_domain_to_response(connector_entity_to_domain(connector, cipher=self.cipher))
        enriched = await self._enrich_connector_responses_for_actor([response], actor)
        return enriched[0]

    async def update_connector_for_actor(
        self,
        *,
        connector_id: int,
        actor: ActorContext,
        name: str | None = None,
        description: str | None = None,
        base_url: str | None = None,
        auth_type: AuthType | None = None,
        auth_config: AuthConfig | dict[str, Any] | None = None,
        rate_policy: RatePolicyDomain | None = None,
        schema_source_type: SchemaSourceType | None = None,
        schema_source_url: str | None = None,
        status: ConnectorStatus | None = None,
        credential_mode: CredentialModeStr | None = None,
        execution_rules: ExecutionRulesDomain | None = None,
    ) -> ApiConnectorResponse:
        connector = await self.connector_repo.get_by_id_and_tenant(connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"ApiConnector not found: {connector_id}")

        can_write = await evaluate_resource_action(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            resource_owner_id=connector.owner_id,
            action=ABAC_ACTION_WRITE,
        )
        if not can_write:
            raise AuthorizationError("Write access denied to API connector")

        if name is not None:
            connector.name = name
        if description is not None:
            connector.description = description
        if base_url is not None:
            connector.base_url = base_url
        if auth_type is not None:
            connector.auth_type = auth_type
        if auth_config is not None:
            # Merge with existing auth_config to preserve unmodified sensitive fields
            from apps.shared.external_systems.api_connector.auth_config_secrets_policy import (
                AUTH_CONFIG_POLICY,
                decrypt_auth_config_from_storage,
                prepare_auth_config_for_storage,
            )
            from apps.shared.utils.secret_engines import merge_config

            existing_decrypted = decrypt_auth_config_from_storage(
                connector.auth_config or {},
                cipher=self.cipher,
            )

            merged_config = merge_config(
                existing_decrypted,
                auth_config_to_dict(auth_config),
                AUTH_CONFIG_POLICY,
            )
            mode = effective_credential_mode(credential_mode or connector.credential_mode)
            if mode == CREDENTIAL_MODE_USER:
                merged_config = strip_connector_auth_user_mode_template(
                    merged_config,
                    auth_type=(auth_type or connector.auth_type),
                )

            connector.auth_config = prepare_auth_config_for_storage(merged_config, cipher=self.cipher)
        if credential_mode is not None:
            connector.credential_mode = credential_mode
        if rate_policy is not None:
            connector.rate_policy = self._to_rate_policy_dict(rate_policy)
        if execution_rules is not None:
            connector.execution_rules = execution_rules.to_dict()
        if schema_source_type is not None:
            connector.schema_source_type = schema_source_type
        if schema_source_url is not None:
            connector.schema_source_url = schema_source_url
        if status is not None:
            connector.status = status

        from apps.shared.external_systems.api_connector.auth_config_secrets_policy import (
            decrypt_auth_config_from_storage,
        )

        final_auth_config = decrypt_auth_config_from_storage(
            connector.auth_config or {},
            cipher=self.cipher,
        )
        self._validate_auth_config(
            connector.auth_type,
            final_auth_config,
            credential_mode=effective_credential_mode(connector.credential_mode),
        )
        connector.updated_at = datetime.now(UTC)
        updated = await self.connector_repo.update(connector)
        updated_with_owner = await self.connector_repo.get_by_id_and_tenant(updated.id, self.tenant_id)
        response = connector_domain_to_response(
            connector_entity_to_domain(updated_with_owner or updated, cipher=self.cipher)
        )
        # Same enrichment as get/list — UI replaces the list row with this payload.
        enriched = await self._enrich_connector_responses_for_actor([response], actor)
        return enriched[0]

    @transaction
    async def delete_connector_for_actor(self, *, connector_id: int, actor: ActorContext) -> None:
        connector = await self.connector_repo.get_by_id_and_tenant(connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"ApiConnector not found: {connector_id}")

        can_write = await evaluate_resource_action(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            resource_owner_id=connector.owner_id,
            action=ABAC_ACTION_WRITE,
        )
        if not can_write:
            raise AuthorizationError("Write access denied to API connector")

        await self._cleanup_connector_dependents(connector_id=connector.id)
        await self.operation_repo.delete_by_connector(self.tenant_id, connector_id)
        await self.connector_repo.delete(connector)

    async def _cleanup_connector_dependents(self, *, connector_id: int) -> None:
        """Remove polymorphic dependents that have no FK cascade to api_connectors."""
        operations = await self.operation_repo.list_by_connector(self.tenant_id, connector_id)
        operation_ids = [operation.id for operation in operations]
        if operation_ids:
            await self._operation_index_writer.remove_for_operation_ids(operation_ids)

        deleted_bindings = await UserIntegrationCredentialRepository(self.db_session).delete_bindings_for_resource(
            tenant_id=self.tenant_id,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector_id,
        )
        if deleted_bindings:
            logger.info(
                "Deleted %s user integration credential(s) for api connector %s",
                deleted_bindings,
                connector_id,
            )

        await self.db_session.execute(
            delete(AclGrant).where(
                AclGrant.tenant_id == self.tenant_id,
                AclGrant.resource_type == RESOURCE_TYPE_API_CONNECTOR,
                AclGrant.resource_id == connector_id,
            )
        )
        await self.db_session.execute(
            delete(ResourceAcl).where(
                ResourceAcl.tenant_id == self.tenant_id,
                ResourceAcl.resource_type == RESOURCE_TYPE_API_CONNECTOR,
                ResourceAcl.resource_id == connector_id,
            )
        )
        await TagBindingRepository(self.db_session).delete_by_resource(
            self.tenant_id,
            RESOURCE_TYPE_API_CONNECTOR,
            connector_id,
        )
        await self.db_session.flush()

    async def sync_operations_from_schema_for_actor(
        self,
        *,
        connector_id: int,
        actor: ActorContext,
        file_content: str | None = None,
    ) -> SyncSchemaSummaryDTO:
        connector = await self.connector_repo.get_by_id_and_tenant(connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"ApiConnector not found: {connector_id}")

        can_write = await evaluate_resource_action(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            resource_owner_id=connector.owner_id,
            action=ABAC_ACTION_WRITE,
        )
        if not can_write:
            raise AuthorizationError("Write access denied to API connector")

        schema = await SchemaSourceResolver.resolve(
            source_type=connector.schema_source_type,
            source_url=connector.schema_source_url,
            file_content=file_content,
        )
        if schema is None:
            return SyncSchemaSummaryDTO(added=0, updated=0, staled=0, unchanged=0)

        specs = OpenApiParser(schema).parse()
        schema_metadata = self._extract_schema_metadata(schema=schema, specs=specs)
        existing_imported = await self.operation_repo.list_imported_by_connector(self.tenant_id, connector.id)
        existing_by_upstream_key = {row.upstream_key: row for row in existing_imported if row.upstream_key}

        incoming_by_upstream_key: dict[str, ApiOperationDomain] = {}
        for spec in specs:
            draft = imported_operation_domain_from_spec(
                connector_id=connector.id,
                owner_id=connector.owner_id,
                spec=spec,
            )
            incoming_by_upstream_key[draft.upstream_key] = draft

        added = 0
        updated = 0
        unchanged = 0
        now = datetime.now(UTC)
        for upstream_key, draft in incoming_by_upstream_key.items():
            current = existing_by_upstream_key.get(upstream_key)
            if current is None:
                saved = await self.create_operation_domain(draft)
                await self._operation_index_writer.create_for_operation(saved)
                added += 1
                continue

            current_domain = operation_entity_to_domain(current)
            if not current_domain.needs_openapi_resync(draft):
                unchanged += 1
                continue

            updated_domain = current_domain.apply_openapi_import(draft, at=now)
            await self.update_operation_domain(updated_domain)
            await self._operation_index_writer.refresh_for_operation(updated_domain)
            updated += 1

        staled = 0
        # Mark upstream-removed imported operations as stale.
        for upstream_key, existing in existing_by_upstream_key.items():
            if upstream_key in incoming_by_upstream_key:
                continue
            if existing.status == OPERATION_STATUS_STALE:
                continue
            stale_domain = operation_entity_to_domain(existing).marked_stale(at=now)
            await self.update_operation_domain(stale_domain)
            await self._operation_index_writer.remove_for_operation(stale_domain)
            staled += 1

        connector.schema_metadata = schema_metadata
        connector.schema_last_synced_at = datetime.now(UTC)
        await self.connector_repo.update(connector)
        return SyncSchemaSummaryDTO(
            added=added,
            updated=updated,
            staled=staled,
            unchanged=unchanged,
        )

    async def install_integration_pack_for_actor(
        self,
        *,
        actor: ActorContext,
        manifest: ApiConnectorPackManifest,
        oauth: InstallPackOAuthInput,
    ) -> tuple[ApiConnectorResponse, PackSyncSummaryDTO]:
        return await install_integration_pack(self, actor=actor, manifest=manifest, oauth=oauth)

    async def sync_installed_pack_for_connector_for_actor(
        self,
        *,
        actor: ActorContext,
        connector_id: int,
        catalog: IntegrationPackCatalog[ApiConnectorPackManifest],
    ) -> tuple[ApiConnectorResponse, PackSyncSummaryDTO]:
        return await sync_installed_pack_for_connector(
            self, actor=actor, connector_id=connector_id, catalog=catalog
        )

    async def apply_pack_manifest_for_actor(
        self,
        *,
        connector_id: int,
        actor: ActorContext,
        manifest: ApiConnectorPackManifest,
    ) -> tuple[ApiConnectorResponse, PackSyncSummaryDTO]:
        return await apply_pack_manifest(self, connector_id=connector_id, actor=actor, manifest=manifest)

    async def require_write_access_for_actor(self, actor: ActorContext, connector: ApiConnectorDomain) -> None:
        allowed = await evaluate_resource_action(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            resource_owner_id=connector.owner_id,
            action=ABAC_ACTION_WRITE,
        )
        if not allowed:
            raise AuthorizationError("Write access denied to API connector")

    async def get_connector_domain(self, connector_id: int) -> ApiConnectorDomain | None:
        return await self.connector_repo.get_domain_by_id_and_tenant(
            connector_id,
            self.tenant_id,
            cipher=self.cipher,
        )

    async def get_connector_by_pack_ref(self, pack_ref: str) -> ApiConnectorDomain | None:
        return await self.connector_repo.get_domain_by_pack_ref(self.tenant_id, pack_ref, cipher=self.cipher)

    async def save_connector_pack_metadata(self, connector: ApiConnectorDomain) -> None:
        row = await self.connector_repo.get_by_id_and_tenant(connector.id, self.tenant_id)
        if row is None:
            raise ResourceNotFoundError(f"Api connector not found: {connector.id}")
        apply_connector_pack_metadata_to_entity(row, connector)
        await self.connector_repo.update(row)

    async def sync_pack_oauth_scopes(self, connector_id: int, manifest_scopes: list[str]) -> tuple[bool, bool]:
        from apps.shared.external_systems.api_connector.auth_config_secrets_policy import (
            decrypt_auth_config_from_storage,
            prepare_auth_config_for_storage,
        )

        row = await self.connector_repo.get_by_id_and_tenant(connector_id, self.tenant_id)
        if row is None:
            raise ResourceNotFoundError(f"Api connector not found: {connector_id}")
        if row.auth_type != AUTH_TYPE_OAUTH2:
            return False, False

        decrypted = decrypt_auth_config_from_storage(row.auth_config or {}, cipher=self.cipher)
        old_scopes = set(decrypted.get("scopes") or [])
        new_scopes = set(manifest_scopes)
        if old_scopes == new_scopes:
            return False, False

        decrypted["scopes"] = list(manifest_scopes)
        row.auth_config = prepare_auth_config_for_storage(decrypted, cipher=self.cipher)
        await self.connector_repo.update(row)
        return True, bool(new_scopes - old_scopes)

    async def list_operation_domains_for_connector(self, connector_id: int) -> list[ApiOperationDomain]:
        rows = await self.operation_repo.list_by_connector(self.tenant_id, connector_id)
        return [operation_entity_to_domain(row) for row in rows]

    async def create_operation_domain(self, operation: ApiOperationDomain) -> ApiOperationDomain:
        entity = operation_domain_to_new_entity(operation, tenant_id=self.tenant_id)
        await self.operation_repo.create(entity)
        return operation_entity_to_domain(entity)

    async def update_operation_domain(self, operation: ApiOperationDomain) -> None:
        entity = await self.operation_repo.get_by_id_and_tenant(operation.id, self.tenant_id)
        if entity is None:
            raise ResourceNotFoundError(f"Api operation not found: {operation.id}")
        apply_operation_domain_to_entity(entity, operation)
        await self.operation_repo.update(entity)

    async def refresh_operation_resource_index(self, operation: ApiOperationDomain) -> None:
        await self._operation_index_writer.refresh_for_operation(operation)

    async def remove_operation_resource_index(self, operation: ApiOperationDomain) -> None:
        await self._operation_index_writer.remove_for_operation(operation)

    async def delete_operation_by_id(self, operation_id: int) -> None:
        entity = await self.operation_repo.get_by_id_and_tenant(operation_id, self.tenant_id)
        if entity is None:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")
        await self.operation_repo.delete(entity)

    async def _load_operation_domain_or_raise(self, operation_id: int) -> ApiOperationDomain:
        entity = await self.operation_repo.get_by_id_and_tenant(operation_id, self.tenant_id)
        if entity is None:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")
        return operation_entity_to_domain(entity)

    async def _require_operation_write_access(
        self,
        *,
        actor: ActorContext,
        operation_id: int,
    ) -> ApiOperationDomain:
        domain = await self._load_operation_domain_or_raise(operation_id)
        connector = await self.get_connector_domain(domain.connector_id)
        if connector is None:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")
        await self.require_write_access_for_actor(actor, connector)
        return domain

    async def add_manual_operation_for_actor(
        self,
        *,
        connector_id: int,
        actor: ActorContext,
        method: str,
        path_template: str,
        operation_id: str | None,
        summary: str,
        description: str | None,
        tags: list[str] | None,
        request_schema: dict[str, Any] | None,
        response_schema: dict[str, Any] | None,
        auth_requirement: AuthRequirement = AUTH_REQUIREMENT_REQUIRED,
        risk_level: RiskLevel = RISK_LEVEL_MEDIUM,
    ) -> ApiOperationDomain:
        connector = await self.get_connector_domain(connector_id)
        if connector is None:
            raise ResourceNotFoundError(f"ApiConnector not found: {connector_id}")
        await self.require_write_access_for_actor(actor, connector)

        method_upper = method.upper()
        if method_upper not in ALLOWED_HTTP_METHODS:
            raise ValidationError(f"Unsupported method: {method}")
        if not request_schema:
            raise ValidationError("request_schema is required for manual operation")
        if not response_schema:
            raise ValidationError("response_schema is required for manual operation")

        domain = manual_operation_domain_from_values(
            connector_id=connector_id,
            owner_id=actor.user_id,
            method=method_upper,
            path_template=path_template,
            operation_id=operation_id,
            summary=summary,
            description=description,
            tags=tags or [],
            request_schema=request_schema,
            response_schema=response_schema,
            auth_requirement=auth_requirement,
            risk_level=risk_level,
        )
        created = await self.create_operation_domain(domain)
        await self._operation_index_writer.create_for_operation(created)
        return created

    async def update_operation_status_for_actor(
        self,
        *,
        operation_id: int,
        actor: ActorContext,
        status: OperationStatus,
    ) -> ApiOperationDomain:
        if status not in {OPERATION_STATUS_ACTIVE, OPERATION_STATUS_DISABLED}:
            raise ValidationError("Only active/disabled statuses are allowed for operation status updates")

        domain = await self._require_operation_write_access(actor=actor, operation_id=operation_id)
        updated = replace(domain, status=status, updated_at=datetime.now(UTC))
        await self.update_operation_domain(updated)
        await self.refresh_operation_resource_index(updated)
        return updated

    async def update_operation_for_actor(
        self,
        *,
        operation_id: int,
        actor: ActorContext,
        method: str | None = None,
        path_template: str | None = None,
        operation_id_new: str | None = None,
        summary: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        request_schema: dict[str, Any] | None = None,
        response_schema: dict[str, Any] | None = None,
        auth_requirement: AuthRequirement | None = None,
        risk_level: RiskLevel | None = None,
    ) -> ApiOperationDomain:
        domain = await self._require_operation_write_access(actor=actor, operation_id=operation_id)
        if domain.source != OPERATION_SOURCE_MANUAL:
            raise ValidationError("Imported operations cannot be edited. Disable and add a manual operation instead")

        updates: dict[str, Any] = {}
        if method is not None:
            method_upper = method.upper()
            if method_upper not in ALLOWED_HTTP_METHODS:
                raise ValidationError(f"Unsupported method: {method}")
            updates["method"] = method_upper
        if path_template is not None:
            updates["path_template"] = path_template
        if operation_id_new is not None:
            updates["operation_id"] = operation_id_new
        if summary is not None:
            updates["summary"] = summary
        if description is not None:
            updates["description"] = description
        if tags is not None:
            updates["tags"] = tags
        if request_schema is not None:
            updates["request_schema"] = request_schema
        if response_schema is not None:
            updates["response_schema"] = response_schema
        if auth_requirement is not None:
            updates["auth_requirement"] = auth_requirement
        if risk_level is not None:
            updates["risk_level"] = risk_level

        updated = replace(domain, **updates)
        seed = f"{updated.method}:{updated.path_template}:{updated.operation_id or ''}"
        operation_uid = ApiOperationDomain.build_operation_uid(
            connector_id=updated.connector_id,
            seed=seed,
            source=OPERATION_SOURCE_MANUAL,
        )
        with_uid = replace(updated, operation_uid=operation_uid, updated_at=datetime.now(UTC))
        with_hash = replace(with_uid, content_hash=with_uid.spec_content_hash())
        await self.update_operation_domain(with_hash)
        if with_hash.status == OPERATION_STATUS_ACTIVE:
            await self._operation_index_writer.create_for_operation(with_hash)
        return with_hash

    async def delete_operation_for_actor(self, *, operation_id: int, actor: ActorContext) -> None:
        domain = await self._require_operation_write_access(actor=actor, operation_id=operation_id)
        if domain.source != OPERATION_SOURCE_MANUAL:
            raise ValidationError("Imported operations cannot be deleted. Disable and add a manual operation instead")

        await self.remove_operation_resource_index(domain)
        await self.delete_operation_by_id(operation_id)

    async def list_operations_for_actor(
        self,
        *,
        connector_id: int,
        actor: ActorContext,
        page: int = 1,
        page_size: int = 10,
        status: OperationStatus | None = None,
        query: str | None = None,
    ) -> tuple[list[ApiOperationDomain], PaginationRequest]:
        return await self._query_operations_for_actor(
            actor=actor,
            query=query,
            connector_id=connector_id,
            page=page,
            page_size=page_size,
            status=status,
            require_connector_scope=True,
        )

    async def get_operation_stats_for_actor(
        self,
        *,
        connector_id: int,
        actor: ActorContext,
    ) -> ApiOperationStatsResponse:
        await self.get_connector_for_actor(
            connector_id=connector_id,
            actor=actor,
        )
        stats = await self.operation_repo.get_connector_operation_stats(
            tenant_id=self.tenant_id,
            connector_id=connector_id,
        )
        return ApiOperationStatsResponse(**stats)

    async def search_operations_for_actor(
        self,
        *,
        query: str | None,
        actor: ActorContext,
        connector_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
        status: OperationStatus | None = OPERATION_STATUS_ACTIVE,
    ) -> tuple[list[ApiOperationDomain], PaginationRequest]:
        return await self._query_operations_for_actor(
            actor=actor,
            query=query,
            connector_id=connector_id,
            page=page,
            page_size=page_size,
            status=status,
            require_connector_scope=False,
        )

    async def _query_operations_for_actor(
        self,
        *,
        actor: ActorContext,
        query: str | None,
        connector_id: int | None,
        page: int,
        page_size: int,
        status: OperationStatus | None,
        require_connector_scope: bool,
    ) -> tuple[list[ApiOperationDomain], PaginationRequest]:
        scoped_connector_ids: list[int] | None = None
        if connector_id is not None:
            await self.get_connector_for_actor(
                connector_id=connector_id,
                actor=actor,
            )
            scoped_connector_ids = [connector_id]
        elif require_connector_scope:
            raise ValidationError("connector_id is required")
        else:
            scoped_connector_ids = await self._readable_connector_ids_for_actor(actor=actor)
            if not scoped_connector_ids:
                pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=0)
                return [], pagination

        total = await self.operation_repo.count_search(
            tenant_id=self.tenant_id,
            query=query,
            connector_id=connector_id,
            scoped_connector_ids=scoped_connector_ids,
            status=status,
        )

        if total == 0:
            pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=0)
            return [], pagination

        pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=total)

        rows = await self.operation_repo.search(
            tenant_id=self.tenant_id,
            query=query,
            connector_id=connector_id,
            scoped_connector_ids=scoped_connector_ids,
            status=status,
            limit=pagination.page_size,
            offset=pagination.offset,
        )

        # Batch fetch ResourceIndex for all operations
        operation_ids = [op.id for op in rows]
        resource_index_map = await self._get_resource_index_repo().list_by_resources(
            self.tenant_id,
            RESOURCE_TYPE_API_CONNECTOR,
            operation_ids,
        )

        return [operation_entity_to_domain(row, resource_index_map.get(row.id)) for row in rows], pagination

    async def get_operation_for_actor(
        self,
        *,
        operation_uid: str,
        actor: ActorContext,
    ) -> ApiOperationDomain:
        operation = await self.operation_repo.get_by_uid_and_tenant(operation_uid, self.tenant_id)
        if not operation:
            raise ResourceNotFoundError(f"Api operation not found: {operation_uid}")

        connector = await self.connector_repo.get_by_id_and_tenant(operation.connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"Api operation not found: {operation_uid}")

        allowed = await evaluate_resource_action(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            resource_owner_id=connector.owner_id,
            action=ABAC_ACTION_READ,
        )
        if not allowed:
            raise AuthorizationError("Access denied to API operation")

        # Fetch ResourceIndex for vector sync status
        resource_index = await self._get_resource_index_repo().get_by_resource(
            self.tenant_id,
            RESOURCE_TYPE_API_CONNECTOR,
            operation.id,
        )
        return operation_entity_to_domain(operation, resource_index)

    async def get_operation_by_id_for_actor(
        self,
        *,
        operation_id: int,
        actor: ActorContext,
    ) -> tuple[ApiOperationDomain, ApiConnectorDomain]:
        """Fetch operation by internal DB id and return it with its connector info."""
        operation = await self.operation_repo.get_by_id_and_tenant(operation_id, self.tenant_id)
        if not operation:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")

        connector = await self.connector_repo.get_by_id_and_tenant(operation.connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")

        allowed = await evaluate_resource_action(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            resource_owner_id=connector.owner_id,
            action=ABAC_ACTION_READ,
        )
        if not allowed:
            raise AuthorizationError("Access denied to API operation")

        # Fetch ResourceIndex for vector sync status
        resource_index = await self._get_resource_index_repo().get_by_resource(
            self.tenant_id,
            RESOURCE_TYPE_API_CONNECTOR,
            operation.id,
        )
        return operation_entity_to_domain(operation, resource_index), connector_entity_to_domain(
            connector, cipher=self.cipher
        )

    @staticmethod
    def _to_rate_policy_dict(rate_policy: RatePolicyDomain | None) -> dict[str, Any]:
        if rate_policy is None:
            return {}
        return rate_policy.to_policy_dict()

    @staticmethod
    def _extract_schema_metadata(
        *,
        schema: dict[str, Any],
        specs: list[OperationSpec],
    ) -> dict[str, Any]:
        info_raw = schema.get("info") if isinstance(schema.get("info"), dict) else {}
        contact_raw = info_raw.get("contact") if isinstance(info_raw.get("contact"), dict) else {}
        license_raw = info_raw.get("license") if isinstance(info_raw.get("license"), dict) else {}

        servers_raw = schema.get("servers") if isinstance(schema.get("servers"), list) else []
        top_level_tags = schema.get("tags") if isinstance(schema.get("tags"), list) else []

        servers = [
            {
                "url": str(server.get("url")),
                "description": server.get("description") if isinstance(server.get("description"), str) else None,
            }
            for server in servers_raw
            if isinstance(server, dict) and isinstance(server.get("url"), str)
        ]

        tags = [
            str(tag.get("name")) for tag in top_level_tags if isinstance(tag, dict) and isinstance(tag.get("name"), str)
        ]

        return {
            "openapi_version": schema.get("openapi") or schema.get("swagger"),
            "title": info_raw.get("title") if isinstance(info_raw.get("title"), str) else None,
            "description": info_raw.get("description") if isinstance(info_raw.get("description"), str) else None,
            "version": info_raw.get("version") if isinstance(info_raw.get("version"), str) else None,
            "terms_of_service": info_raw.get("termsOfService")
            if isinstance(info_raw.get("termsOfService"), str)
            else None,
            "contact": {
                "name": contact_raw.get("name") if isinstance(contact_raw.get("name"), str) else None,
                "email": contact_raw.get("email") if isinstance(contact_raw.get("email"), str) else None,
                "url": contact_raw.get("url") if isinstance(contact_raw.get("url"), str) else None,
            },
            "license": {
                "name": license_raw.get("name") if isinstance(license_raw.get("name"), str) else None,
                "url": license_raw.get("url") if isinstance(license_raw.get("url"), str) else None,
            },
            "servers": servers,
            "tags": tags,
            "path_count": len({spec.path_template for spec in specs}),
            "operation_count": len(specs),
        }

    @staticmethod
    def _merge_auth_config(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        """Merge incoming auth_config with existing; preserve secrets unless client sends a new value."""
        from apps.shared.external_systems.api_connector.auth_config_secrets_policy import AUTH_CONFIG_POLICY
        from apps.shared.utils.secret_engines import merge_config

        return merge_config(existing, incoming, AUTH_CONFIG_POLICY)

    @staticmethod
    def _validate_auth_config(
        auth_type: AuthType,
        auth_config: dict[str, Any],
        *,
        credential_mode: CredentialModeStr = CREDENTIAL_MODE_SHARED,
    ) -> None:
        """Validate auth_config structure based on auth_type.

        Provides clear error messages for configuration issues while maintaining
        flexibility for different auth types.

        Args:
            auth_type: The authentication type (none, api_key, bearer, basic, custom)
            auth_config: The authentication configuration dictionary

        Raises:
            ValidationError: If the auth_config is invalid for the given auth_type
        """
        if auth_type == "none":
            # No validation needed for none
            return

        if auth_type == AUTH_TYPE_OAUTH2:
            if credential_mode != CREDENTIAL_MODE_USER:
                raise ValidationError("OAuth2 API connectors require credential_mode='user'")
            missing_fields = [
                field for field in ("authorize_url", "token_url", "client_id") if not auth_config.get(field)
            ]
            if missing_fields:
                raise ValidationError(f"OAuth2 auth requires: {', '.join(missing_fields)}")
            return

        if credential_mode == CREDENTIAL_MODE_USER and auth_type in ("api_key", "bearer", "basic"):
            return

        if auth_type == "api_key":
            if not auth_config.get("key_value") and not auth_config.get("api_key"):
                raise ValidationError("API Key auth requires 'key_value' or 'api_key' field in auth_config")

        elif auth_type == "bearer":
            if not auth_config.get("token") and not auth_config.get("access_token"):
                raise ValidationError("Bearer auth requires 'token' or 'access_token' field in auth_config")

        elif auth_type == "basic":
            if not auth_config.get("username") or not auth_config.get("password"):
                raise ValidationError("Basic auth requires both 'username' and 'password' fields in auth_config")

        elif auth_type == "custom":
            # Validate required fields for custom/session-based auth
            missing_fields = []

            if not auth_config.get("login_endpoint"):
                missing_fields.append("login_endpoint")

            if not auth_config.get("login_payload_template"):
                missing_fields.append("login_payload_template")

            if not auth_config.get("token_extraction"):
                missing_fields.append("token_extraction")

            if not auth_config.get("request_headers"):
                missing_fields.append("request_headers")

            if not auth_config.get("extra_config"):
                missing_fields.append("extra_config")

            if missing_fields:
                raise ValidationError(
                    f"Custom auth requires the following fields in auth_config: {', '.join(missing_fields)}. "
                    f"See documentation for session-based authentication configuration."
                )

            # Validate that token_extraction has at least one token path
            token_extraction = auth_config.get("token_extraction", {})
            if not isinstance(token_extraction, dict) or len(token_extraction) == 0:
                raise ValidationError(
                    "Custom auth 'token_extraction' must be a non-empty dict mapping token names to extraction paths"
                )
