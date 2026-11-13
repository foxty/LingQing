"""Data source management service.

Handles CRUD operations for tenant data sources and assets including:
- Data source connections (SQLite, PostgreSQL, etc.)
- Asset metadata (tables, views, etc.)
- CSV uploads and queries
"""

from copy import deepcopy
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement
from sqlglot.errors import ParseError

from apps.shared.authz.authz_query_builder import (
    AuthzSqlFilter,
    build_unified_resource_filter,
    evaluate_resource_action,
)
from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError, ValidationError
from apps.shared.db.models import AssetMetadata, DataSource, ResourceIndex
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    ABAC_ACTION_WRITE,
    RESOURCE_TYPE_DATA_SOURCE,
    AbacAction,
)
from apps.shared.domain.value_objects import DataSourceType
from apps.shared.external_systems.credentials.resolver import IntegrationCredentialResolver
from apps.shared.external_systems.data_source.adapters import (
    db_data_source_to_domain,
    db_data_source_to_domain_with_connection,
    db_data_source_to_public_api_response,
)
from apps.shared.external_systems.data_source.catalog_sync import (
    METADATA_SYNC_CONFIG_KEY,
    CatalogSyncCredentials,
    strip_user_mode_connection_template,
)
from apps.shared.external_systems.data_source.domain import DataSourceDomain
from apps.shared.external_systems.data_source.schemas import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
    DiscoveredAsset,
    TestConnectionResponse,
)
from apps.shared.external_systems.domain.types import (
    CREDENTIAL_MODE_USER,
    IntegrationPurpose,
    effective_credential_mode,
)
from apps.shared.infra.analytics_db import create_db_manager_from_config
from apps.shared.infra.analytics_db.manager_factory import get_db_manager_for_datasource
from apps.shared.utils.logger import get_logger
from apps.shared.utils.pagination import PaginationRequest
from apps.shared.utils.sql_utils import extract_table_references, validate_read_only_sql

from .repository import (
    AssetMetadataRepository,
    DataSourceRepository,
)
from .temp_table_repository import TempTableRepository

logger = get_logger(__name__)

_SYSTEM_CATALOG_SCHEMAS = frozenset({"information_schema", "pg_catalog", "pg_toast"})


@dataclass(frozen=True)
class AssetAccessScope:
    deny_all: bool
    allow_all: bool
    asset_filter: ColumnElement[bool] | None
    index_parent_filter: ColumnElement[bool] | None


class DataSourceService(TenantAwareService):
    """Service for managing tenant data sources.

    All operations are automatically scoped to the tenant context.
    """

    def __init__(
        self,
        tenant_id: int,
        data_source_repo: DataSourceRepository,
        asset_repo: AssetMetadataRepository,
        credential_resolver: IntegrationCredentialResolver | None = None,
    ):
        """Initialize data source service.

        Args:
            tenant_id: Tenant ID for all operations
            data_source_repo: Data source repository for data access
            asset_repo: Asset repository for data access
            credential_resolver: BYOT resolver (optional; lazy default if omitted)
        """
        super().__init__(tenant_id)
        self.data_source_repo = data_source_repo
        self.asset_repo = asset_repo
        self._credential_resolver = credential_resolver

    async def has_data_source_manage_permission_for_actor(self, *, actor: ActorContext) -> bool:
        return await role_has_permission(
            db=self.data_source_repo.db,
            tenant_id=actor.tenant_id,
            role_key=actor.user_role,
            permission=TenantAppPermissions.DATA_SOURCES_MANAGE,
        )

    async def _build_data_source_auth_scope(
        self,
        *,
        actor: ActorContext,
        action: AbacAction,
    ) -> AuthzSqlFilter:
        has_manage = await self.has_data_source_manage_permission_for_actor(actor=actor)
        return await build_unified_resource_filter(
            db_session=self.data_source_repo.db,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            action=action,
            resource_model=DataSource,
            has_manage_permission=has_manage,
        )

    async def build_asset_access_scope(self, *, actor: ActorContext, action: AbacAction) -> AssetAccessScope:
        """Resolve which assets are visible based on data-source-level authz."""
        scope = await self._build_data_source_auth_scope(actor=actor, action=action)
        if scope.deny_all:
            return AssetAccessScope(
                deny_all=True,
                allow_all=False,
                asset_filter=None,
                index_parent_filter=None,
            )
        if scope.allow_all:
            return AssetAccessScope(
                deny_all=False,
                allow_all=True,
                asset_filter=None,
                index_parent_filter=None,
            )

        allowed_data_sources = (
            select(DataSource.id)
            .where(
                DataSource.tenant_id == self.tenant_id,
                scope.clause,
            )
            .scalar_subquery()
        )
        asset_filter = AssetMetadata.data_source_id.in_(allowed_data_sources)
        index_parent_filter = ResourceIndex.parent_id.in_(allowed_data_sources)
        return AssetAccessScope(
            deny_all=False,
            allow_all=False,
            asset_filter=asset_filter,
            index_parent_filter=index_parent_filter,
        )

    async def require_asset_access(
        self,
        *,
        asset_id: int,
        actor: ActorContext,
        action: AbacAction,
    ) -> int:
        """Ensure the actor can access an asset via its data source."""
        stmt = (
            select(AssetMetadata.data_source_id)
            .join(DataSource, DataSource.id == AssetMetadata.data_source_id)
            .where(
                DataSource.tenant_id == self.tenant_id,
                AssetMetadata.id == asset_id,
            )
        )
        data_source_id = await self.data_source_repo.db.scalar(stmt)
        if data_source_id is None:
            raise ResourceNotFoundError(f"Asset {asset_id} not found")
        await self.require_data_source_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            action=action,
        )
        return data_source_id

    async def require_data_source_access_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
        action: AbacAction,
    ) -> tuple[DataSourceDomain, bool]:
        data_source = await self._get_data_source_domain(data_source_id)
        if not data_source:
            raise ResourceNotFoundError(f"Data source {data_source_id} not found")

        has_manage_permission = await self.has_data_source_manage_permission_for_actor(actor=actor)
        allowed = await evaluate_resource_action(
            db_session=self.data_source_repo.db,
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=data_source_id,
            resource_owner_id=data_source.owner_id,
            action=action,
            has_manage_permission=has_manage_permission,
        )
        if not allowed:
            raise AuthorizationError("无权访问该数据源")

        return data_source, has_manage_permission

    async def require_read_access_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
    ) -> DataSourceDomain:
        data_source, _ = await self.require_data_source_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            action=ABAC_ACTION_READ,
        )
        return data_source

    async def require_write_access_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
    ) -> tuple[DataSourceDomain, bool]:
        return await self.require_data_source_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            action=ABAC_ACTION_WRITE,
        )

    async def require_asset_curate_access_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
    ) -> DataSourceDomain:
        """Write + for per-user external sources, only owner or tenant managers may curate assets."""
        data_source, has_manage_permission = await self.require_write_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
        )
        if (
            not data_source.managed
            and effective_credential_mode(data_source.credential_mode) == CREDENTIAL_MODE_USER
            and not has_manage_permission
            and data_source.owner_id != actor.user_id
        ):
            raise AuthorizationError(
                "Only the data source owner can manage the asset catalog for per-user data sources.",
            )
        return data_source

    async def _list_data_source_rows_for_actor(
        self,
        *,
        actor: ActorContext,
        page: int | None = None,
        page_size: int | None = None,
        query: str | None = None,
    ) -> tuple[list[DataSource], PaginationRequest | None]:
        """ABAC-scoped data source rows; paginate when page and page_size are set."""
        auth_scope = await self._build_data_source_auth_scope(actor=actor, action=ABAC_ACTION_READ)
        if auth_scope.deny_all:
            if page is not None and page_size is not None:
                return [], PaginationRequest.with_total(page=page, page_size=page_size, total=0)
            return [], None

        scope_clause = None if auth_scope.allow_all else auth_scope.clause
        if page is None or page_size is None:
            rows = await self.data_source_repo.list_by_tenant(
                self.tenant_id,
                scope_clause=scope_clause,
            )
            return rows, None

        total = await self.data_source_repo.count_by_tenant_filtered(
            self.tenant_id,
            scope_clause=scope_clause,
            query=query,
        )
        pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=total)
        if total == 0:
            return [], pagination

        rows = await self.data_source_repo.list_by_tenant_paginated(
            self.tenant_id,
            limit=pagination.page_size,
            offset=pagination.offset,
            scope_clause=scope_clause,
            query=query,
        )
        return rows, pagination

    async def _domains_from_rows_enriched(
        self,
        rows: list[DataSource],
        actor: ActorContext,
    ) -> list[DataSourceDomain]:
        domains = [d for d in (db_data_source_to_domain(row) for row in rows) if d is not None]
        await self._enrich_domains_user_connection_status(domains, actor)
        return domains

    async def list_data_sources_for_actor(self, *, actor: ActorContext) -> list[DataSourceDomain]:
        rows, _ = await self._list_data_source_rows_for_actor(actor=actor)
        return await self._domains_from_rows_enriched(rows, actor)

    async def list_data_source_responses_paginated_for_actor(
        self,
        *,
        actor: ActorContext,
        page: int,
        page_size: int,
        query: str | None = None,
    ) -> tuple[list[DataSourceResponse], PaginationRequest]:
        """Paginated data sources as redacted API responses (includes user connection status)."""
        rows, pagination = await self._list_data_source_rows_for_actor(
            actor=actor,
            page=page,
            page_size=page_size,
            query=query,
        )
        if pagination is None:
            pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=len(rows))
        domains = await self._domains_from_rows_enriched(rows, actor)
        status_by_id = {domain.id: domain.user_connection_status for domain in domains}
        items: list[DataSourceResponse] = []
        for entity in rows:
            response = db_data_source_to_public_api_response(entity)
            status = status_by_id.get(entity.id)
            if status is not None:
                response = response.model_copy(update={"user_connection_status": status})
            items.append(response)
        return items, pagination

    async def get_data_source_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
    ) -> DataSourceResponse:
        await self.require_read_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
        )
        entity = await self.data_source_repo.get_by_id_and_tenant(data_source_id, self.tenant_id)
        if entity is None:
            raise ResourceNotFoundError(f"Data source {data_source_id} not found")
        response = db_data_source_to_public_api_response(entity)
        return await self.enrich_data_source_response_for_actor(response, actor)

    async def enrich_data_source_response_for_actor(
        self,
        response: DataSourceResponse,
        actor: ActorContext,
    ) -> DataSourceResponse:
        status = await self._user_connection_status_for_data_source(
            data_source_id=response.id,
            managed=response.managed,
            credential_mode=response.credential_mode,
            actor=actor,
        )
        if status is None:
            return response
        return response.model_copy(update={"user_connection_status": status})

    async def _enrich_domains_user_connection_status(
        self,
        domains: list[DataSourceDomain],
        actor: ActorContext,
    ) -> None:
        """Attach actor-scoped user_connection_status on BYOT external domains (in place)."""
        for domain in domains:
            domain.user_connection_status = await self._user_connection_status_for_data_source(
                data_source_id=domain.id,
                managed=domain.managed,
                credential_mode=domain.credential_mode,
                actor=actor,
            )

    async def _user_connection_status_for_data_source(
        self,
        *,
        data_source_id: int,
        managed: bool,
        credential_mode: str,
        actor: ActorContext,
    ) -> str | None:
        if managed or credential_mode != CREDENTIAL_MODE_USER:
            return None
        resolver = self._credential_resolver or IntegrationCredentialResolver(self.data_source_repo.db)
        status, _ = await resolver.connection_status_for_actor(
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=data_source_id,
        )
        return status

    async def update_data_source_for_actor(
        self,
        *,
        data_source_id: int,
        update_data: DataSourceUpdate,
        actor: ActorContext,
    ) -> DataSourceResponse:
        await self.require_write_access_for_actor(data_source_id=data_source_id, actor=actor)

        config = update_data.config
        credential_mode = update_data.credential_mode
        entity = await self.data_source_repo.get_by_id_and_tenant(data_source_id, self.tenant_id)
        mode = effective_credential_mode(
            credential_mode or (entity.credential_mode if entity else None)
        )
        if config is not None:
            base = dict(entity.config or {}) if entity else {}
            merged = CatalogSyncCredentials.merge_incoming_into_config(base, config)
            if mode == CREDENTIAL_MODE_USER:
                config = strip_user_mode_connection_template(merged)
            else:
                config = merged
        elif mode == CREDENTIAL_MODE_USER and entity and entity.config:
            config = strip_user_mode_connection_template(entity.config)

        updated = await self.data_source_repo.update_fields(
            data_source_id=data_source_id,
            tenant_id=self.tenant_id,
            name=update_data.name,
            description=update_data.description,
            config=config,
            credential_mode=credential_mode,
        )
        if not updated:
            raise ResourceNotFoundError(f"Data source {data_source_id} not found")

        logger.info(f"Updated data source {data_source_id} for tenant {self.tenant_id}")
        return db_data_source_to_public_api_response(updated)

    async def delete_data_source_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
    ) -> bool:
        data_source, has_manage_permission = await self.require_write_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
        )

        # Prevent deletion of managed data sources
        if data_source.managed:
            raise ValueError("Cannot delete managed data sources")

        if not has_manage_permission and data_source.owner_id != actor.user_id:
            raise AuthorizationError("只能删除自己创建的数据源")

        if data_source.has_assets():
            logger.warning(f"Deleting data source {data_source_id} with assets for tenant {self.tenant_id}")
            raise ValueError("Cannot delete data source with existing assets. Please delete assets first.")

        deleted = await self.data_source_repo.delete_by_id_and_tenant(data_source_id, self.tenant_id)
        logger.info(f"Deleted data source {data_source_id} for tenant {self.tenant_id}")
        return deleted

    async def query_asset_for_actor(
        self,
        *,
        data_source_id: int,
        asset_name: str,
        actor: ActorContext,
        sql: str | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        data_source = await self.require_read_access_for_actor(data_source_id=data_source_id, actor=actor)

        if not data_source.managed or data_source.type != DataSourceType.SQLITE:
            raise ValueError(f"Data source {data_source_id} is not a managed SQLite analytics table")

        asset = await self.asset_repo.get_by_data_source_and_name(data_source_id, asset_name)
        if not asset:
            raise ValueError(f"Asset '{asset_name}' not found in data source {data_source_id}")

        async with get_db_manager_for_datasource(data_source) as db:
            if sql:
                return await db.query(sql)
            return await db.query(f'SELECT * FROM "{asset_name}" LIMIT {limit}')

    async def _get_data_source_domain(self, data_source_id: int) -> DataSourceDomain | None:
        """Get data source as domain model (internal use only).

        Args:
            data_source_id: Data source ID

        Returns:
            DataSourceDomain if found, None otherwise
        """
        data_source = await self.data_source_repo.get_by_id_and_tenant(data_source_id, self.tenant_id)
        return db_data_source_to_domain(data_source) if data_source else None

    async def get_db_manager_for_actor(self, data_source_id: int, actor: ActorContext):
        """Database manager using resolved credentials for user-mode external sources."""
        entity = await self.data_source_repo.get_by_id_and_tenant(data_source_id, self.tenant_id)
        if entity is None:
            raise ValueError(f"Data source {data_source_id} not found for tenant {self.tenant_id}")

        resolver = self._credential_resolver or IntegrationCredentialResolver(self.data_source_repo.db)
        resolved_config = await resolver.resolve_data_source_config(
            data_source=entity,
            actor=actor,
            purpose=IntegrationPurpose.QUERY,
        )
        domain = db_data_source_to_domain_with_connection(entity, resolved_config)
        return get_db_manager_for_datasource(domain)

    async def get_db_manager(self, data_source_id: int):
        """Get database manager for a data source.

        Factory method that returns the appropriate DB manager implementation
        based on data source type. This encapsulates infrastructure details
        and provides tenant-scoped access control.

        Args:
            data_source_id: Data source ID

        Returns:
            Context manager that yields AnalyticsDBManager instance

        Raises:
            ValueError: If data source not found or config is invalid

        Example:
            async with await service.get_db_manager(data_source_id) as db:
                df = await db.query("SELECT * FROM table")
        """
        entity = await self.data_source_repo.get_by_id_and_tenant(data_source_id, self.tenant_id)
        if entity is None:
            raise ValueError(f"Data source {data_source_id} not found for tenant {self.tenant_id}")
        mode = effective_credential_mode(entity.credential_mode)
        if mode == CREDENTIAL_MODE_USER and not entity.managed:
            raise ValidationError(
                "User-mode data sources require an actor; use get_db_manager_for_actor instead.",
            )
        data_source = db_data_source_to_domain(entity)
        if data_source is None:
            raise ValueError(f"Data source {data_source_id} not found")
        if data_source.tenant_id != self.tenant_id:
            raise AuthorizationError(f"Data source {data_source_id} does not belong to tenant {self.tenant_id}")

        return get_db_manager_for_datasource(data_source)

    async def get_db_manager_for_metadata_sync(self, data_source_id: int):
        """DB manager for catalog operations (discover, metadata sync, scheduler)."""
        entity = await self.data_source_repo.get_by_id_and_tenant(data_source_id, self.tenant_id)
        if entity is None:
            raise ValueError(f"Data source {data_source_id} not found for tenant {self.tenant_id}")

        mode = effective_credential_mode(entity.credential_mode)
        if entity.managed or mode != CREDENTIAL_MODE_USER:
            return await self.get_db_manager(data_source_id)

        domain_entity = db_data_source_to_domain(entity)
        if domain_entity is None or not domain_entity.catalog_sync_ready():
            raise ValidationError(
                "Per-user data sources require metadata_sync credentials for catalog sync and discovery.",
            )
        connection = domain_entity.connection_config_for_metadata_sync(entity.config or {})
        domain = db_data_source_to_domain_with_connection(entity, connection)
        if domain.tenant_id != self.tenant_id:
            raise AuthorizationError(f"Data source {data_source_id} does not belong to tenant {self.tenant_id}")
        return get_db_manager_for_datasource(domain)

    async def create_data_source(self, data_source_data: DataSourceCreate, owner_id: int) -> DataSourceResponse:
        """Create a new data source for the tenant.

        Args:
            data_source_data: Data source creation data

        Returns:
            Created DataSourceResponse DTO

        Raises:
            ValueError: If data source with same name already exists
        """
        # Check if data source name already exists for this tenant
        existing = await self.data_source_repo.get_by_tenant_and_name(self.tenant_id, data_source_data.name)

        if existing:
            raise ValueError(f"Data source '{data_source_data.name}' already exists for tenant {self.tenant_id}")

        config = data_source_data.config or {}
        credential_mode = effective_credential_mode(data_source_data.credential_mode)
        if credential_mode == CREDENTIAL_MODE_USER:
            config = strip_user_mode_connection_template(config)

        data_source = await self.data_source_repo.create_from_domain(
            tenant_id=self.tenant_id,
            name=data_source_data.name,
            type=data_source_data.type,
            managed=data_source_data.managed,
            config=config,
            description=data_source_data.description,
            owner_id=owner_id,
            credential_mode=credential_mode,
        )

        logger.info(f"Created data source '{data_source.name}' (ID: {data_source.id}) for tenant {self.tenant_id}")
        return db_data_source_to_public_api_response(data_source)

    async def query_data_for_actor(
        self,
        data_source_id: int,
        sql_query: str,
        *,
        actor: ActorContext,
        params: dict | None = None,
        max_rows: int | None = None,
    ) -> pd.DataFrame:
        """Execute read-only query with data-source and registered-asset authorization."""
        validate_read_only_sql(sql_query)
        await self.require_read_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
        )
        await self.require_registered_assets_in_sql(data_source_id=data_source_id, sql_query=sql_query)

        db_manager = await self.get_db_manager_for_actor(data_source_id, actor)
        async with db_manager:
            df = await db_manager.query(sql_query, params=params)

        if max_rows is not None and len(df) > max_rows:
            logger.info(f"Query returned {len(df)} rows; truncating to max_rows={max_rows} for tenant {self.tenant_id}")
            return df.head(max_rows)

        return df

    async def require_registered_assets_in_sql(self, *, data_source_id: int, sql_query: str) -> None:
        """Fail closed when SQL references tables not registered as assets on the data source."""
        try:
            table_refs = extract_table_references(sql_query)
        except ParseError as err:
            raise ValidationError("Unable to parse SQL for table access validation.") from err

        for table_ref in sorted(table_refs):
            asset = await self._resolve_asset_for_table_ref(data_source_id, table_ref)
            if asset is None:
                raise AuthorizationError(f"Query references unregistered asset '{table_ref}'.")

    @staticmethod
    def _table_ref_lookup_candidates(table_ref: str) -> list[str]:
        """Build asset_name lookup candidates; skip bare suffix for system catalog refs."""
        candidates = [table_ref, table_ref.lower()]
        parts = table_ref.split(".")
        if len(parts) > 1 and parts[0].lower() not in _SYSTEM_CATALOG_SCHEMAS:
            tail = parts[-1]
            candidates.extend([tail, tail.lower()])
        return candidates

    async def _resolve_asset_for_table_ref(self, data_source_id: int, table_ref: str):
        tried: set[str] = set()
        for candidate in self._table_ref_lookup_candidates(table_ref):
            if candidate in tried:
                continue
            tried.add(candidate)
            asset = await self.asset_repo.get_by_data_source_and_name(data_source_id, candidate)
            if asset:
                return asset
        return None

    async def drop_managed_table_for_actor(
        self,
        *,
        data_source_id: int,
        asset_name: str,
        actor: ActorContext,
    ) -> bool:
        await self.require_write_access_for_actor(data_source_id=data_source_id, actor=actor)
        """Drop a managed table from the database.

        This is a low-level operation that only handles the database table drop.
        Asset metadata cleanup should be handled by AssetMetadataService.

        Args:
            data_source_id: Data source ID
            asset_name: Asset name (table name)

        Returns:
            True if table was dropped, False if table doesn't exist

        Raises:
            ValueError: If data source not found or not managed
        """
        data_source = await self._get_data_source_domain(data_source_id)

        if not data_source:
            raise ValueError(f"Data source {data_source_id} not found")

        if not data_source.managed:
            raise ValueError(f"Data source {data_source_id} is not managed")

        async with get_db_manager_for_datasource(data_source) as db:
            if await db.table_exists(asset_name):
                await db.drop_table(asset_name)
                logger.info(f"Dropped table '{asset_name}' for tenant {self.tenant_id}")
                return True
            else:
                logger.warning(f"Table '{asset_name}' does not exist in database")
                return False

    async def test_connection(self, db_type: str, config: dict) -> TestConnectionResponse:
        """Test database connection without saving.

        Args:
            db_type: Database type
            config: Connection configuration

        Returns:
            TestConnectionResponse DTO
        """
        try:
            if db_type in [DataSourceType.POSTGRES, DataSourceType.MYSQL, DataSourceType.DATABRICKS]:
                async with create_db_manager_from_config(self.tenant_id, db_type, config) as manager:
                    success, message = await manager.test_connection()
                    return TestConnectionResponse(
                        success=success,
                        message=message,
                        error=None if success else message,
                    )
            return TestConnectionResponse(
                success=False,
                message=f"Unsupported database type: {db_type}",
                error=None,
            )

        except Exception as e:
            logger.error(f"Connection test failed: {e}", exc_info=True)
            return TestConnectionResponse(
                success=False,
                message="Connection test failed",
                error=str(e),
            )

    async def test_saved_data_source_connection(
        self,
        data_source_id: int,
        config_overlay: dict | None = None,
    ) -> TestConnectionResponse:
        """Test connection for a saved data source (merges stored secrets when overlay uses placeholders)."""
        entity = await self.data_source_repo.get_by_id_and_tenant(data_source_id, self.tenant_id)
        if entity is None:
            raise ResourceNotFoundError(f"Data source {data_source_id} not found")
        if entity.managed:
            raise ValidationError("Platform-managed data sources cannot be tested with this endpoint.")

        merged = deepcopy(entity.config or {})
        if config_overlay:
            merged = CatalogSyncCredentials.merge_incoming_into_config(merged, config_overlay)
            for key, value in config_overlay.items():
                if key != METADATA_SYNC_CONFIG_KEY:
                    merged[key] = value

        mode = effective_credential_mode(entity.credential_mode)
        if mode == CREDENTIAL_MODE_USER:
            if not CatalogSyncCredentials.is_configured_in_config(merged, data_source_type=entity.type):
                return TestConnectionResponse(
                    success=False,
                    message="Sync login username and password are required.",
                    error="Sync login not configured",
                )
            connection = CatalogSyncCredentials.merge_connection_config(merged)
        else:
            connection = merged

        try:
            domain = db_data_source_to_domain_with_connection(entity, connection)
            if domain is None:
                raise ValueError(f"Data source {data_source_id} is invalid")
            async with get_db_manager_for_datasource(domain) as manager:
                success, message = await manager.test_connection()
                return TestConnectionResponse(
                    success=success,
                    message=message,
                    error=None if success else message,
                )
        except Exception as e:
            logger.error(f"Saved data source connection test failed: {e}", exc_info=True)
            return TestConnectionResponse(
                success=False,
                message="Connection test failed",
                error=str(e),
            )

    async def discover_assets_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
        query: str | None = None,
        include_schema: bool = True,
    ) -> tuple[list[DiscoveredAsset], int, bool]:
        """Discover available assets from a data source.

        Args:
            data_source_id: Data source ID
            actor: Caller used for tenant access checks
            query: Optional search query
            include_schema: Whether to include schema metadata

        Returns:
            Tuple of (assets, total, requires_query). requires_query is true when the
            engine refuses an unscoped list and the query is too short to run.

        Raises:
            ValueError: If data source not found or discovery fails
        """
        await self.require_asset_curate_access_for_actor(data_source_id=data_source_id, actor=actor)
        entity = await self.data_source_repo.get_by_id_and_tenant(data_source_id, self.tenant_id)
        if entity is None:
            raise ValueError(f"Data source {data_source_id} not found")

        mode = effective_credential_mode(entity.credential_mode)
        if not entity.managed and mode == CREDENTIAL_MODE_USER:
            db_manager = await self.get_db_manager_for_metadata_sync(data_source_id)
        else:
            db_manager = await self.get_db_manager_for_actor(data_source_id, actor)
        async with db_manager as manager:
            if manager.requires_search_query() and not manager.search_query_is_runnable(query):
                return [], 0, True
            assets, total = await manager.discover_assets(
                query=query,
                include_schema=include_schema,
            )
            return assets, total, False

    async def discover_assets_by_names_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
        asset_names: list[str],
    ) -> list[DiscoveredAsset]:
        """Discover metadata for specific assets by name (catalog curation)."""
        await self.require_asset_curate_access_for_actor(data_source_id=data_source_id, actor=actor)
        entity = await self.data_source_repo.get_by_id_and_tenant(data_source_id, self.tenant_id)
        if entity is None:
            raise ValueError(f"Data source {data_source_id} not found")

        if not asset_names:
            return []

        mode = effective_credential_mode(entity.credential_mode)
        if not entity.managed and mode == CREDENTIAL_MODE_USER:
            db_manager = await self.get_db_manager_for_metadata_sync(data_source_id)
        else:
            db_manager = await self.get_db_manager_for_actor(data_source_id, actor)

        discovered: list[DiscoveredAsset] = []
        async with db_manager as manager:
            for asset_name in asset_names:
                asset = await manager.discover_asset(asset_name)
                if asset:
                    discovered.append(asset)

        return discovered

    async def cleanup_expired_temp_tables(self, temp_table_repo: TempTableRepository) -> dict[str, int]:
        """Cleanup expired temporary tables for this tenant.

        This method handles the business logic for cleaning up expired temp tables:
        1. Query expired temp table metadata
        2. Drop tables from Analytics DB
        3. Delete metadata records
        4. Return cleanup statistics

        Args:
            temp_table_repo: Repository for temp table metadata operations

        Returns:
            Dictionary with cleanup statistics: cleaned, errors, skipped, total_processed
        """
        cleaned_count = 0
        error_count = 0
        skipped_count = 0

        expired_tables = await temp_table_repo.get_expired_tables()

        if not expired_tables:
            logger.info(f"No expired temp tables to clean up for tenant {self.tenant_id}")
            return {"cleaned": 0, "errors": 0, "skipped": 0, "total_processed": 0}

        # Filter by tenant
        tenant_expired = [t for t in expired_tables if t.tenant_id == self.tenant_id]

        if not tenant_expired:
            logger.info(f"No expired temp tables for tenant {self.tenant_id}")
            return {"cleaned": 0, "errors": 0, "skipped": 0, "total_processed": 0}

        logger.info(f"Found {len(tenant_expired)} expired temp tables to clean up for tenant {self.tenant_id}")

        for temp_meta in tenant_expired:
            try:
                # Get DB manager for the data source
                try:
                    db_manager = await self.get_db_manager(temp_meta.data_source_id)
                except ValueError:
                    logger.warning(
                        f"Data source {temp_meta.data_source_id} not found, "
                        f"removing metadata for table '{temp_meta.table_name}'"
                    )
                    await temp_table_repo.delete_metadata(temp_meta)
                    skipped_count += 1
                    continue

                # Drop table from database
                async with db_manager:
                    if await db_manager.table_exists(temp_meta.table_name):
                        await db_manager.drop_table(temp_meta.table_name)
                        logger.info(
                            f"Dropped expired temp table '{temp_meta.table_name}' "
                            f"from tenant {self.tenant_id} Analytics DB"
                        )
                    else:
                        logger.warning(
                            f"Temp table '{temp_meta.table_name}' not found in database, removing metadata only"
                        )

                # Delete metadata
                await temp_table_repo.delete_metadata(temp_meta)
                cleaned_count += 1

            except Exception as e:
                logger.error(f"Failed to cleanup temp table '{temp_meta.table_name}': {e}", exc_info=True)
                error_count += 1

        summary = {
            "cleaned": cleaned_count,
            "errors": error_count,
            "skipped": skipped_count,
            "total_processed": len(tenant_expired),
        }

        logger.info(
            f"Temp table cleanup completed for tenant {self.tenant_id}: "
            f"{cleaned_count} cleaned, {error_count} errors, {skipped_count} skipped"
        )

        return summary
