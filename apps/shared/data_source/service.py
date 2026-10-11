"""Data source management service.

Handles CRUD operations for tenant data sources and assets including:
- Data source connections (SQLite, PostgreSQL, etc.)
- Asset metadata (tables, views, etc.)
- CSV uploads and queries
"""

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.sql.elements import ColumnElement

from apps.shared.authz.authz_query_builder import (
    AuthzSqlFilter,
    build_unified_resource_filter,
)
from apps.shared.authz.delegation import allows_delegated_read
from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import role_has_permission
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.shared.data_source.adapters import (
    db_data_source_to_domain,
    domain_data_source_to_api,
)
from apps.shared.data_source.domain import DataSourceDomain
from apps.shared.data_source.schemas import (
    DataSourceCreate,
    DataSourceResponse,
    DataSourceUpdate,
    DiscoveredAsset,
    TestConnectionResponse,
)
from apps.shared.db.models import AssetMetadata, DataSource, ResourceIndex
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    ABAC_ACTION_WRITE,
    RESOURCE_TYPE_DATA_SOURCE,
    AbacAction,
)
from apps.shared.domain.value_objects import DataSourceType
from apps.shared.infra.analytics_db import create_db_manager_from_config
from apps.shared.infra.analytics_db.manager_factory import get_db_manager_for_datasource
from apps.shared.utils.logger import get_logger
from apps.shared.utils.pagination import PaginationRequest
from apps.shared.utils.sql_utils import validate_read_only_sql

from .repository import (
    AssetMetadataRepository,
    DataSourceRepository,
)
from .temp_table_repository import TempTableRepository

logger = get_logger(__name__)


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
    ):
        """Initialize data source service.

        Args:
            tenant_id: Tenant ID for all operations
            data_source_repo: Data source repository for data access
            asset_repo: Asset repository for data access
        """
        super().__init__(tenant_id)
        self.data_source_repo = data_source_repo
        self.asset_repo = asset_repo

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
        delegated_ids: list[int] | None = None,
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
            delegated_ids=delegated_ids,
        )
        return data_source_id

    async def require_data_source_access_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
        action: AbacAction,
        delegated_ids: list[int] | None = None,
    ) -> tuple[DataSourceDomain, bool]:
        data_source = await self._get_data_source_domain(data_source_id)
        if not data_source:
            raise ResourceNotFoundError(f"Data source {data_source_id} not found")

        has_manage_permission = await self.has_data_source_manage_permission_for_actor(actor=actor)
        allowed = await allows_delegated_read(
            db_session=self.data_source_repo.db,
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=data_source_id,
            resource_owner_id=data_source.owner_id,
            action=action,
            has_manage_permission=has_manage_permission,
            delegated_ids=delegated_ids,
        )
        if not allowed:
            raise AuthorizationError("无权访问该数据源")

        return data_source, has_manage_permission

    async def require_read_access_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
        delegated_ids: list[int] | None = None,
    ) -> DataSourceDomain:
        data_source, _ = await self.require_data_source_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            action=ABAC_ACTION_READ,
            delegated_ids=delegated_ids,
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

    async def list_data_sources_for_actor(self, *, actor: ActorContext) -> list[DataSourceDomain]:
        has_manage_permission = await self.has_data_source_manage_permission_for_actor(actor=actor)
        auth_scope = await build_unified_resource_filter(
            db_session=self.data_source_repo.db,
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            action=ABAC_ACTION_READ,
            resource_model=DataSource,
            has_manage_permission=has_manage_permission,
        )
        if auth_scope.deny_all:
            return []

        scope_clause = None if auth_scope.allow_all else auth_scope.clause
        data_sources = await self.data_source_repo.list_by_tenant(
            self.tenant_id,
            scope_clause=scope_clause,
        )
        return [db_data_source_to_domain(ds) for ds in data_sources]

    async def list_data_sources_paginated_for_actor(
        self,
        *,
        actor: ActorContext,
        page: int,
        page_size: int,
        query: str | None = None,
    ) -> tuple[list[DataSourceDomain], PaginationRequest]:
        """List tenant data sources with pagination and optional search query."""
        has_manage_permission = await self.has_data_source_manage_permission_for_actor(actor=actor)
        auth_scope = await build_unified_resource_filter(
            db_session=self.data_source_repo.db,
            tenant_id=actor.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            action=ABAC_ACTION_READ,
            resource_model=DataSource,
            has_manage_permission=has_manage_permission,
        )
        if auth_scope.deny_all:
            return [], PaginationRequest.with_total(page=page, page_size=page_size, total=0)

        scope_clause = None if auth_scope.allow_all else auth_scope.clause
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
        return [db_data_source_to_domain(ds) for ds in rows], pagination

    async def get_data_source_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
        delegated_ids: list[int] | None = None,
    ) -> DataSourceResponse:
        data_source = await self.require_read_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            delegated_ids=delegated_ids,
        )
        return domain_data_source_to_api(data_source)

    async def update_data_source_for_actor(
        self,
        *,
        data_source_id: int,
        update_data: DataSourceUpdate,
        actor: ActorContext,
    ) -> DataSourceResponse:
        await self.require_write_access_for_actor(data_source_id=data_source_id, actor=actor)

        updated = await self.data_source_repo.update_fields(
            data_source_id=data_source_id,
            tenant_id=self.tenant_id,
            name=update_data.name,
            description=update_data.description,
            config=update_data.config,
        )
        if not updated:
            raise ResourceNotFoundError(f"Data source {data_source_id} not found")

        logger.info(f"Updated data source {data_source_id} for tenant {self.tenant_id}")
        return domain_data_source_to_api(db_data_source_to_domain(updated))

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
        data_source = await self._get_data_source_domain(data_source_id)
        if data_source.tenant_id != self.tenant_id:
            raise AuthorizationError(f"Data source {data_source_id} does not belong to tenant {self.tenant_id}")
        if not data_source:
            raise ValueError(f"Data source {data_source_id} not found for tenant {self.tenant_id}")

        return get_db_manager_for_datasource(data_source)

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

        # Create data source record first (without db_url)
        data_source = await self.data_source_repo.create_from_domain(
            tenant_id=self.tenant_id,
            name=data_source_data.name,
            type=data_source_data.type,
            managed=data_source_data.managed,
            config=data_source_data.config or {},
            description=data_source_data.description,
            owner_id=owner_id,
        )

        logger.info(f"Created data source '{data_source.name}' (ID: {data_source.id}) for tenant {self.tenant_id}")
        return domain_data_source_to_api(db_data_source_to_domain(data_source))

    async def query_data_for_actor(
        self,
        data_source_id: int,
        sql_query: str,
        *,
        actor: ActorContext,
        params: dict | None = None,
        max_rows: int | None = None,
        delegated_ids: list[int] | None = None,
    ) -> pd.DataFrame:
        """Execute read-only query with data-source-level authorization.

        Authorization behavior:
        - When `actor` is provided, the caller must have read access to the data source.
        - Individual table references are not checked separately; assets inherit data source access.
        - ``delegated_ids`` optionally expands read for one agent turn; omit on HTTP callers.
        """
        validate_read_only_sql(sql_query)
        await self.require_read_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            delegated_ids=delegated_ids,
        )

        db_manager = await self.get_db_manager(data_source_id)
        async with db_manager:
            df = await db_manager.query(sql_query, params=params)

        if max_rows is not None and len(df) > max_rows:
            logger.info(f"Query returned {len(df)} rows; truncating to max_rows={max_rows} for tenant {self.tenant_id}")
            return df.head(max_rows)

        return df

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
        await self.require_read_access_for_actor(data_source_id=data_source_id, actor=actor)
        data_source = await self._get_data_source_domain(data_source_id)
        if not data_source:
            raise ValueError(f"Data source {data_source_id} not found")

        async with get_db_manager_for_datasource(data_source) as manager:
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
        await self.require_read_access_for_actor(data_source_id=data_source_id, actor=actor)
        """Discover metadata for specific assets by name.

        Args:
            data_source_id: Data source ID
            asset_names: List of asset names to discover

        Returns:
            List of discovered assets (schema included)

        Raises:
            ValueError: If data source not found
        """
        data_source = await self._get_data_source_domain(data_source_id)
        if not data_source:
            raise ValueError(f"Data source {data_source_id} not found")

        if not asset_names:
            return []

        discovered: list[DiscoveredAsset] = []
        async with get_db_manager_for_datasource(data_source) as manager:
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
