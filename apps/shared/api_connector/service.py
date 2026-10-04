"""Service layer for API connector management and schema indexing."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.api_connector.adapters import (
    auth_config_to_dict,
    connector_domain_to_response,
    connector_entity_to_domain,
    operation_entity_to_domain,
)
from apps.shared.api_connector.constants import (
    ALLOWED_HTTP_METHODS,
    AUTH_REQUIREMENT_REQUIRED,
    CONNECTOR_STATUS_ACTIVE,
    OPERATION_SOURCE_IMPORTED,
    OPERATION_SOURCE_MANUAL,
    OPERATION_STATUS_ACTIVE,
    OPERATION_STATUS_DISABLED,
    OPERATION_STATUS_STALE,
    RISK_LEVEL_MEDIUM,
)
from apps.shared.api_connector.domain import (
    ApiConnectorDomain,
    ApiOperationDomain,
    AuthConfig,
    AuthRequirement,
    AuthType,
    ConnectorStatus,
    OperationStatus,
    RatePolicyDomain,
    RiskLevel,
    SchemaSourceType,
)
from apps.shared.api_connector.repository import ApiConnectorRepository, ApiOperationIndexRepository
from apps.shared.api_connector.schema_parser import OpenApiParser, OperationSpec, SchemaSourceResolver
from apps.shared.api_connector.schemas import (
    ApiConnectorResponse,
    ApiOperationStatsResponse,
    SyncSchemaSummaryDTO,
)
from apps.shared.authz.authz_query_builder import build_unified_resource_filter, evaluate_resource_action
from apps.shared.authz.delegation import allows_delegated_read
from apps.shared.core.exceptions import (
    AuthorizationError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.core.transaction import transaction
from apps.shared.db.models import ApiConnector, ApiOperationIndex
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    ABAC_ACTION_WRITE,
    RESOURCE_TYPE_API_CONNECTOR,
)
from apps.shared.search.repository import ResourceIndexRepository
from apps.shared.search.schemas import ResourceIndexCreateDTO
from apps.shared.utils.field_cipher import AUTH_CONFIG_SENSITIVE_FIELDS, FieldCipher

if TYPE_CHECKING:
    from apps.shared.search.indexing_service import ResourceIndexService
from apps.shared.utils.logger import get_logger
from apps.shared.utils.pagination import PaginationRequest

logger = get_logger(__name__)


class ApiConnectorService:
    """Manages API connectors and operation index lifecycle."""

    def __init__(self, tenant_id: int, db_session: AsyncSession):
        self.tenant_id = tenant_id
        self.db_session = db_session
        self.connector_repo = ApiConnectorRepository(db_session)
        self.operation_repo = ApiOperationIndexRepository(db_session)
        self.cipher = FieldCipher()
        self._resource_index_service: ResourceIndexService | None = None
        self._resource_index_repo: ResourceIndexRepository | None = None

    async def _get_resource_index_service(self) -> ResourceIndexService:
        """Lazy-initialize ResourceIndexService."""
        if self._resource_index_service is None:
            from apps.shared.search.indexing_service import ResourceIndexService

            self._resource_index_service = await ResourceIndexService.create(
                tenant_id=self.tenant_id,
                db_session=self.db_session,
            )
        return self._resource_index_service

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
    ) -> ApiConnectorDomain:
        existing = await self.connector_repo.get_by_tenant_and_name(self.tenant_id, name)
        if existing:
            raise DuplicateResourceError(f"API connector already exists: {name}")

        auth_config_dict = auth_config_to_dict(auth_config)
        self._validate_auth_config(auth_type, auth_config_dict)

        encrypted_auth = self.cipher.encrypt_dict(auth_config_dict, sensitive_fields=AUTH_CONFIG_SENSITIVE_FIELDS)

        connector = ApiConnector(
            tenant_id=self.tenant_id,
            owner_id=owner_id,
            name=name,
            description=description,
            base_url=base_url,
            auth_type=auth_type,
            auth_config=encrypted_auth,
            rate_policy=self._to_rate_policy_dict(rate_policy),
            schema_source_type=schema_source_type,
            schema_source_url=schema_source_url,
            status=CONNECTOR_STATUS_ACTIVE,
        )
        created = await self.connector_repo.create(connector)
        created_with_owner = await self.connector_repo.get_by_id_and_tenant(created.id, self.tenant_id)
        return connector_domain_to_response(
            connector_entity_to_domain(created_with_owner or created, cipher=self.cipher)
        )

    async def list_connectors_for_actor(self, *, actor: ActorContext) -> list[ApiConnectorResponse]:
        """List connectors for actor, returning response DTOs directly."""
        abac_scope = await build_unified_resource_filter(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            action=ABAC_ACTION_READ,
            resource_model=ApiConnector,
        )
        if abac_scope.deny_all:
            return []

        rows = await self.connector_repo.list_by_tenant(
            self.tenant_id,
            scope_clause=abac_scope.clause,
        )
        if abac_scope.allow_all:
            return [connector_domain_to_response(connector_entity_to_domain(row, cipher=self.cipher)) for row in rows]

        # Fallback path (small result size): per-row authorization check for correctness.
        allowed: list[ApiConnectorResponse] = []
        for row in rows:
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
                allowed.append(connector_domain_to_response(connector_entity_to_domain(row, cipher=self.cipher)))
        return allowed

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
        return connector_domain_to_response(connector_entity_to_domain(connector, cipher=self.cipher))

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
            existing_decrypted = self.cipher.decrypt_dict(
                connector.auth_config or {}, sensitive_fields=AUTH_CONFIG_SENSITIVE_FIELDS
            )

            # Filter out masked values from incoming auth_config
            # If UI sends masked value (e.g., "sk****key"), keep the original decrypted value
            merged_config = self._merge_auth_config(existing_decrypted, auth_config_to_dict(auth_config))

            connector.auth_config = self.cipher.encrypt_dict(
                merged_config, sensitive_fields=AUTH_CONFIG_SENSITIVE_FIELDS
            )
        if rate_policy is not None:
            connector.rate_policy = self._to_rate_policy_dict(rate_policy)
        if schema_source_type is not None:
            connector.schema_source_type = schema_source_type
        if schema_source_url is not None:
            connector.schema_source_url = schema_source_url
        if status is not None:
            connector.status = status

        connector.updated_at = datetime.now(UTC)
        updated = await self.connector_repo.update(connector)
        updated_with_owner = await self.connector_repo.get_by_id_and_tenant(updated.id, self.tenant_id)
        return connector_domain_to_response(
            connector_entity_to_domain(updated_with_owner or updated, cipher=self.cipher)
        )

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

        await self.operation_repo.delete_by_connector(self.tenant_id, connector_id)
        await self.connector_repo.delete(connector)

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

        incoming_by_upstream_key: dict[str, tuple[OperationSpec, str]] = {}
        for spec in specs:
            upstream_key = self._build_upstream_key(
                method=spec.method,
                path_template=spec.path_template,
            )
            content_hash = self._build_operation_content_hash(spec)
            incoming_by_upstream_key[upstream_key] = (spec, content_hash)

        added = 0
        updated = 0
        unchanged = 0
        for upstream_key, (spec, content_hash) in incoming_by_upstream_key.items():
            current = existing_by_upstream_key.get(upstream_key)
            operation_uid = self._build_operation_uid(
                connector_id=connector.id,
                seed=upstream_key,
                source=OPERATION_SOURCE_IMPORTED,
            )
            if current is None:
                entity = ApiOperationIndex(
                    tenant_id=self.tenant_id,
                    connector_id=connector.id,
                    owner_id=connector.owner_id,
                    operation_uid=operation_uid,
                    method=spec.method,
                    path_template=spec.path_template,
                    operation_id=spec.operation_id,
                    summary=spec.summary,
                    description=spec.description,
                    tags=spec.tags,
                    request_schema=spec.request_schema,
                    response_schema=spec.response_schema,
                    auth_requirement=spec.auth_requirement,
                    source=OPERATION_SOURCE_IMPORTED,
                    upstream_key=upstream_key,
                    content_hash=content_hash,
                    status=OPERATION_STATUS_ACTIVE,
                )
                await self.operation_repo.create(entity)
                await self._create_api_operation_resource_index(entity)
                added += 1
                continue

            should_update = current.content_hash != content_hash
            if current.status == OPERATION_STATUS_STALE:
                should_update = True

            if should_update:
                current.method = spec.method
                current.path_template = spec.path_template
                current.operation_id = spec.operation_id
                current.summary = spec.summary
                current.description = spec.description
                current.tags = spec.tags
                current.request_schema = spec.request_schema
                current.response_schema = spec.response_schema
                current.auth_requirement = spec.auth_requirement
                current.upstream_key = upstream_key
                current.content_hash = content_hash
                if current.status != OPERATION_STATUS_DISABLED:
                    current.status = OPERATION_STATUS_ACTIVE
                current.updated_at = datetime.now(UTC)
                await self.operation_repo.update(current)
                if current.status == OPERATION_STATUS_ACTIVE:
                    await self._create_api_operation_resource_index(current)
                else:
                    await self._safe_remove_operation_index(current)
                updated += 1
            else:
                unchanged += 1

        staled = 0
        # Mark upstream-removed imported operations as stale.
        for upstream_key, existing in existing_by_upstream_key.items():
            if upstream_key in incoming_by_upstream_key:
                continue
            if existing.status == OPERATION_STATUS_STALE:
                continue
            existing.status = OPERATION_STATUS_STALE
            existing.updated_at = datetime.now(UTC)
            await self.operation_repo.update(existing)
            await self._safe_remove_operation_index(existing)
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

        method_upper = method.upper()
        if method_upper not in ALLOWED_HTTP_METHODS:
            raise ValidationError(f"Unsupported method: {method}")
        if not request_schema:
            raise ValidationError("request_schema is required for manual operation")
        if not response_schema:
            raise ValidationError("response_schema is required for manual operation")

        seed = f"{method_upper}:{path_template}:{operation_id or ''}"
        entity = ApiOperationIndex(
            tenant_id=self.tenant_id,
            connector_id=connector.id,
            owner_id=actor.user_id,
            operation_uid=self._build_operation_uid(
                connector_id=connector.id,
                seed=seed,
                source=OPERATION_SOURCE_MANUAL,
            ),
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
            source=OPERATION_SOURCE_MANUAL,
            upstream_key=None,
            content_hash=None,
            status=OPERATION_STATUS_ACTIVE,
        )
        entity.content_hash = self._build_operation_content_hash_for_entity(entity)
        created = await self.operation_repo.create(entity)
        await self._create_api_operation_resource_index(created)
        return operation_entity_to_domain(created)

    async def update_operation_status_for_actor(
        self,
        *,
        operation_id: int,
        actor: ActorContext,
        status: OperationStatus,
    ) -> ApiOperationDomain:
        if status not in {OPERATION_STATUS_ACTIVE, OPERATION_STATUS_DISABLED}:
            raise ValidationError("Only active/disabled statuses are allowed for operation status updates")

        operation = await self.operation_repo.get_by_id_and_tenant(operation_id, self.tenant_id)
        if not operation:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")

        connector = await self.connector_repo.get_by_id_and_tenant(operation.connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")

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
            raise AuthorizationError("Write access denied to API operation")

        operation.status = status
        operation.updated_at = datetime.now(UTC)
        updated = await self.operation_repo.update(operation)
        if updated.status == OPERATION_STATUS_ACTIVE:
            await self._create_api_operation_resource_index(updated)
        else:
            await self._safe_remove_operation_index(updated)
        return operation_entity_to_domain(updated)

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
        operation = await self.operation_repo.get_by_id_and_tenant(operation_id, self.tenant_id)
        if not operation:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")
        if operation.source != OPERATION_SOURCE_MANUAL:
            raise ValidationError("Imported operations cannot be edited. Disable and add a manual operation instead")

        connector = await self.connector_repo.get_by_id_and_tenant(operation.connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")

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
            raise AuthorizationError("Write access denied to API operation")

        if method is not None:
            method_upper = method.upper()
            if method_upper not in ALLOWED_HTTP_METHODS:
                raise ValidationError(f"Unsupported method: {method}")
            operation.method = method_upper
        if path_template is not None:
            operation.path_template = path_template
        if operation_id_new is not None:
            operation.operation_id = operation_id_new
        if summary is not None:
            operation.summary = summary
        if description is not None:
            operation.description = description
        if tags is not None:
            operation.tags = tags
        if request_schema is not None:
            operation.request_schema = request_schema
        if response_schema is not None:
            operation.response_schema = response_schema
        if auth_requirement is not None:
            operation.auth_requirement = auth_requirement
        if risk_level is not None:
            operation.risk_level = risk_level

        seed = f"{operation.method}:{operation.path_template}:{operation.operation_id or ''}"
        operation.operation_uid = self._build_operation_uid(
            connector_id=operation.connector_id,
            seed=seed,
            source=OPERATION_SOURCE_MANUAL,
        )
        operation.content_hash = self._build_operation_content_hash_for_entity(operation)
        operation.updated_at = datetime.now(UTC)
        updated = await self.operation_repo.update(operation)
        return operation_entity_to_domain(updated)

    async def delete_operation_for_actor(self, *, operation_id: int, actor: ActorContext) -> None:
        operation = await self.operation_repo.get_by_id_and_tenant(operation_id, self.tenant_id)
        if not operation:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")
        if operation.source != OPERATION_SOURCE_MANUAL:
            raise ValidationError("Imported operations cannot be deleted. Disable and add a manual operation instead")

        connector = await self.connector_repo.get_by_id_and_tenant(operation.connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")

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
            raise AuthorizationError("Write access denied to API operation")

        await self._safe_remove_operation_index(operation)
        await self.operation_repo.delete(operation)

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
            connectors = await self.list_connectors_for_actor(actor=actor)
            scoped_connector_ids = [connector.id for connector in connectors]
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
        delegated_ids: list[int] | None = None,
    ) -> ApiOperationDomain:
        operation = await self.operation_repo.get_by_uid_and_tenant(operation_uid, self.tenant_id)
        if not operation:
            raise ResourceNotFoundError(f"Api operation not found: {operation_uid}")

        connector = await self.connector_repo.get_by_id_and_tenant(operation.connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"Api operation not found: {operation_uid}")

        allowed = await allows_delegated_read(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            resource_owner_id=connector.owner_id,
            action=ABAC_ACTION_READ,
            delegated_ids=delegated_ids,
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
        delegated_ids: list[int] | None = None,
    ) -> tuple[ApiOperationDomain, ApiConnectorDomain]:
        """Fetch operation by internal DB id and return it with its connector info."""
        operation = await self.operation_repo.get_by_id_and_tenant(operation_id, self.tenant_id)
        if not operation:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")

        connector = await self.connector_repo.get_by_id_and_tenant(operation.connector_id, self.tenant_id)
        if not connector:
            raise ResourceNotFoundError(f"Api operation not found: {operation_id}")

        allowed = await allows_delegated_read(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_API_CONNECTOR,
            resource_id=connector.id,
            resource_owner_id=connector.owner_id,
            action=ABAC_ACTION_READ,
            delegated_ids=delegated_ids,
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
    def _build_operation_uid(connector_id: int, seed: str, source: str) -> str:
        raw = f"{connector_id}:{source}:{seed}".encode()
        return hashlib.sha256(raw).hexdigest()[:32]

    @staticmethod
    def _build_upstream_key(method: str, path_template: str) -> str:
        # Deduplicate imported operations by HTTP method + URI template.
        seed = f"{method.upper()}|{path_template.strip()}"
        return hashlib.sha256(seed.encode()).hexdigest()[:32]

    @staticmethod
    def _build_operation_content_hash(spec: OperationSpec) -> str:
        return ApiConnectorService._build_operation_content_hash_from_values(
            method=spec.method,
            path_template=spec.path_template,
            operation_id=spec.operation_id,
            summary=spec.summary,
            description=spec.description,
            tags=spec.tags,
            request_schema=spec.request_schema,
            response_schema=spec.response_schema,
            auth_requirement=spec.auth_requirement,
        )

    @staticmethod
    def _build_operation_content_hash_from_values(
        *,
        method: str,
        path_template: str,
        operation_id: str | None,
        summary: str | None,
        description: str | None,
        tags: list[str] | None,
        request_schema: dict[str, Any] | None,
        response_schema: dict[str, Any] | None,
        auth_requirement: str,
    ) -> str:
        payload = {
            "method": method,
            "path_template": path_template,
            "operation_id": operation_id,
            "summary": summary,
            "description": description,
            "tags": tags,
            "request_schema": request_schema,
            "response_schema": response_schema,
            "auth_requirement": auth_requirement,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()[:32]

    @staticmethod
    def _build_operation_content_hash_for_entity(operation: ApiOperationIndex) -> str:
        return ApiConnectorService._build_operation_content_hash_from_values(
            method=operation.method,
            path_template=operation.path_template,
            operation_id=operation.operation_id,
            summary=operation.summary,
            description=operation.description,
            tags=operation.tags,
            request_schema=operation.request_schema,
            response_schema=operation.response_schema,
            auth_requirement=operation.auth_requirement,
        )

    async def _create_api_operation_resource_index(self, operation: ApiOperationIndex) -> None:
        """Create ResourceIndex record for an API operation.

        Flow 1: Use domain method to get searchable text → save as raw_content.
        Tokenization and chunking happen in Flow 2 (sync job).
        """
        try:
            async with self.db_session.begin_nested():
                domain = operation_entity_to_domain(operation)
                searchable_text = domain.to_searchable_text()
                resource_index_svc = await self._get_resource_index_service()

                raw_content = {
                    "text": searchable_text,
                    "meta": {},
                }

            await resource_index_svc.create_or_update(
                ResourceIndexCreateDTO(
                    tenant_id=self.tenant_id,
                    resource_type=RESOURCE_TYPE_API_CONNECTOR,
                    resource_id=operation.id,
                    owner_id=operation.owner_id,
                    raw_content=raw_content,
                    content_updated_at=operation.updated_at,
                    parent_id=operation.connector_id,
                )
            )
        except Exception as exc:
            logger.warning("Failed to create resource index for api operation %d: %s", operation.id, exc)

    async def _delete_api_operation_resource_index(self, operation_id: int) -> None:
        """Delete ResourceIndex record for an API operation."""
        try:
            resource_index_svc = await self._get_resource_index_service()
            await resource_index_svc.delete(RESOURCE_TYPE_API_CONNECTOR, operation_id)
        except Exception as exc:
            logger.warning("Failed to delete resource index for api operation %d: %s", operation_id, exc)

    async def _safe_remove_operation_index(self, operation: ApiOperationIndex) -> None:
        await self._delete_api_operation_resource_index(operation.id)

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
        """Merge incoming auth_config with existing, skipping masked values.

        Recursively merges nested dicts. If a string value in incoming is masked,
        keeps the original value from existing instead.

        Args:
            existing: Decrypted existing auth_config from database
            incoming: New auth_config from UI/API request

        Returns:
            Merged auth_config with masked values replaced by originals
        """
        from apps.shared.utils.field_cipher import FieldCipher

        merged = dict(existing)
        for key, new_value in incoming.items():
            if isinstance(new_value, str):
                # Check if string value is masked
                if FieldCipher.is_masked(new_value):
                    # Skip masked values - keep original from existing
                    logger.debug(f"Skipping masked field '{key}' during connector update")
                    continue
                merged[key] = new_value
            elif isinstance(new_value, dict):
                # Recursively merge nested dicts (e.g., extra_config)
                existing_nested = existing.get(key, {})
                if isinstance(existing_nested, dict):
                    merged[key] = ApiConnectorService._merge_auth_config(existing_nested, new_value)
                else:
                    merged[key] = new_value
            else:
                # Non-dict, non-string values (lists, numbers, etc.) - just copy
                merged[key] = new_value

        return merged

    @staticmethod
    def _validate_auth_config(auth_type: AuthType, auth_config: dict[str, Any]) -> None:
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
