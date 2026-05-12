"""Data source repository."""

from sqlalchemy import String, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from apps.shared.data_source.domain import AssetMetadataDomain
from apps.shared.db.base_repository import BaseRepository
from apps.shared.db.models import AssetMetadata, DataSource
from apps.shared.domain.value_objects import DataSourceType


class DataSourceRepository(BaseRepository[DataSource]):
    """Repository for DataSource CRUD operations.

    Returns DB models (DataSource) for business logic layer.
    """

    def __init__(self, db: AsyncSession):
        """Initialize data source repository.

        Args:
            db: Database session
        """
        super().__init__(DataSource, db)

    async def get_by_tenant_and_name(self, tenant_id: int, name: str) -> DataSource | None:
        """Get data source by tenant ID and name.

        Args:
            tenant_id: Tenant ID
            name: Data source name

        Returns:
            DataSource DB model or None if not found
        """
        result = await self.db.execute(
            select(DataSource).where(
                DataSource.tenant_id == tenant_id,
                DataSource.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant(self, data_source_id: int, tenant_id: int) -> DataSource | None:
        """Get data source by ID and tenant ID.

        Args:
            data_source_id: Data source ID
            tenant_id: Tenant ID

        Returns:
            DataSource DB model or None if not found
        """
        result = await self.db.execute(
            select(DataSource)
            .options(selectinload(DataSource.owner_user))
            .where(
                DataSource.id == data_source_id,
                DataSource.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(
        self,
        tenant_id: int,
        with_assets: bool = False,
        scope_clause: ColumnElement[bool] | None = None,
    ) -> list[DataSource]:
        """List all data sources for a tenant.

        Args:
            tenant_id: Tenant ID
            with_assets: If True, eagerly load assets relationship

        Returns:
            List of DataSource DB models
        """
        stmt = select(DataSource).options(selectinload(DataSource.owner_user)).where(DataSource.tenant_id == tenant_id)

        if scope_clause is not None:
            stmt = stmt.where(scope_clause)

        if with_assets:
            stmt = stmt.options(selectinload(DataSource.assets))

        stmt = stmt.order_by(DataSource.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_tenant_paginated(
        self,
        tenant_id: int,
        *,
        limit: int,
        offset: int,
        scope_clause: ColumnElement[bool] | None = None,
        query: str | None = None,
    ) -> list[DataSource]:
        """List tenant data sources with pagination and optional search filter."""
        stmt = select(DataSource).options(selectinload(DataSource.owner_user)).where(DataSource.tenant_id == tenant_id)

        if scope_clause is not None:
            stmt = stmt.where(scope_clause)

        normalized_query = query.strip() if query else None
        if normalized_query:
            pattern = f"%{normalized_query}%"
            stmt = stmt.where(
                or_(
                    DataSource.name.ilike(pattern),
                    DataSource.type.ilike(pattern),
                    DataSource.description.ilike(pattern),
                )
            )

        stmt = stmt.order_by(DataSource.created_at.desc()).offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_tenant_filtered(
        self,
        tenant_id: int,
        *,
        scope_clause: ColumnElement[bool] | None = None,
        query: str | None = None,
    ) -> int:
        """Count tenant data sources with optional scope and search filters."""
        stmt = select(func.count(DataSource.id)).where(DataSource.tenant_id == tenant_id)

        if scope_clause is not None:
            stmt = stmt.where(scope_clause)

        normalized_query = query.strip() if query else None
        if normalized_query:
            pattern = f"%{normalized_query}%"
            stmt = stmt.where(
                or_(
                    DataSource.name.ilike(pattern),
                    DataSource.type.ilike(pattern),
                    DataSource.description.ilike(pattern),
                )
            )

        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def list_by_ids(self, data_source_ids: list[int], tenant_id: int) -> list[DataSource]:
        """List data sources by IDs for a tenant.

        Args:
            data_source_ids: Data source IDs
            tenant_id: Tenant ID

        Returns:
            List of DataSource DB models
        """
        if not data_source_ids:
            return []

        result = await self.db.execute(
            select(DataSource)
            .options(selectinload(DataSource.owner_user))
            .where(
                DataSource.id.in_(data_source_ids),
                DataSource.tenant_id == tenant_id,
            )
        )
        return list(result.scalars().all())

    async def create_from_domain(
        self,
        tenant_id: int,
        name: str,
        type: DataSourceType,
        managed: bool,
        config: dict,
        owner_id: int,
        description: str | None = None,
    ) -> DataSource:
        """Create data source from domain parameters.

        Args:
            tenant_id: Tenant ID
            name: Data source name
            type: Data source type
            managed: Whether managed by system
            config: Configuration dict
            description: Optional description

        Returns:
            Created DataSource DB model
        """
        db_ds = DataSource(
            tenant_id=tenant_id,
            name=name,
            type=type,
            managed=managed,
            config=config,
            description=description,
            owner_id=owner_id,
        )
        self.db.add(db_ds)
        await self.db.flush()
        await self.db.refresh(db_ds)
        return db_ds

    async def update_config(self, data_source_id: int, tenant_id: int, config: dict) -> DataSource | None:
        """Update data source config.

        Args:
            data_source_id: Data source ID
            tenant_id: Tenant ID
            config: New config dict

        Returns:
            Updated DataSource DB model or None if not found
        """
        result = await self.db.execute(
            select(DataSource).where(
                DataSource.id == data_source_id,
                DataSource.tenant_id == tenant_id,
            )
        )
        db_ds = result.scalar_one_or_none()
        if not db_ds:
            return None

        db_ds.config = config
        await self.db.flush()
        await self.db.refresh(db_ds)
        return db_ds

    async def update_fields(
        self,
        data_source_id: int,
        tenant_id: int,
        name: str | None = None,
        description: str | None = None,
        config: dict | None = None,
    ) -> DataSource | None:
        """Update data source fields.

        Args:
            data_source_id: Data source ID
            tenant_id: Tenant ID
            name: Optional new name
            description: Optional new description
            config: Optional new config

        Returns:
            Updated DataSource DB model or None if not found
        """
        result = await self.db.execute(
            select(DataSource).where(
                DataSource.id == data_source_id,
                DataSource.tenant_id == tenant_id,
            )
        )
        db_ds = result.scalar_one_or_none()
        if not db_ds:
            return None

        if name is not None:
            db_ds.name = name
        if description is not None:
            db_ds.description = description
        if config is not None:
            db_ds.config = config

        await self.db.flush()
        await self.db.refresh(db_ds)
        return db_ds

    async def delete_by_id_and_tenant(self, data_source_id: int, tenant_id: int) -> bool:
        """Delete data source by ID and tenant.

        Args:
            data_source_id: Data source ID
            tenant_id: Tenant ID

        Returns:
            True if deleted, False if not found
        """
        result = await self.db.execute(
            select(DataSource).where(
                DataSource.id == data_source_id,
                DataSource.tenant_id == tenant_id,
            )
        )
        db_ds = result.scalar_one_or_none()
        if not db_ds:
            return False

        await self.db.delete(db_ds)
        await self.db.flush()
        return True


class AssetMetadataRepository(BaseRepository[AssetMetadata]):
    """Repository for AssetMetadata CRUD operations.

    Returns DB models (AssetMetadata) for business logic layer.
    """

    def __init__(self, db: AsyncSession):
        """Initialize asset metadata repository.

        Args:
            db: Database session
        """
        super().__init__(AssetMetadata, db)

    async def list_sync_candidates_by_tenant(
        self,
        tenant_id: int,
        data_source_ids: list[int] | None = None,
    ) -> list[AssetMetadata]:
        """List assets eligible for metadata sync in a tenant.

        Eligibility rules:
        - Asset belongs to the tenant
        - Data source is external (managed = false)
        - Optional narrowing by data source IDs
        """
        stmt = (
            select(AssetMetadata)
            .join(DataSource)
            .where(
                AssetMetadata.data_source.has(tenant_id=tenant_id),
                DataSource.managed.is_(False),
            )
        )

        if data_source_ids:
            stmt = stmt.where(AssetMetadata.data_source_id.in_(data_source_ids))

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_data_source_and_name(self, data_source_id: int, asset_name: str) -> AssetMetadata | None:
        """Get asset by data source ID and asset name.

        Args:
            data_source_id: Data source ID
            asset_name: Asset name

        Returns:
            AssetMetadata DB model or None if not found
        """
        result = await self.db.execute(
            select(AssetMetadata).where(
                AssetMetadata.data_source_id == data_source_id,
                AssetMetadata.asset_name == asset_name,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id_and_tenant(self, asset_id: int, tenant_id: int) -> AssetMetadata | None:
        result = await self.db.execute(
            select(AssetMetadata)
            .join(DataSource, AssetMetadata.data_source_id == DataSource.id)
            .where(
                AssetMetadata.id == asset_id,
                DataSource.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_data_source(
        self,
        data_source_id: int,
        limit: int | None = None,
        offset: int | None = None,
        abac_filter=None,
    ) -> list[AssetMetadata]:
        """List assets for a data source with optional pagination.

        Args:
            data_source_id: Data source ID
            limit: Maximum number of assets to return (optional, for pagination)
            offset: Number of assets to skip (optional, for pagination)

        Returns:
            List of AssetMetadata DB models
        """
        query = (
            select(AssetMetadata)
            .where(AssetMetadata.data_source_id == data_source_id)
            .order_by(AssetMetadata.created_at.desc())
            .options(selectinload(AssetMetadata.owner_user))
            .execution_options(populate_existing=True)
        )

        if abac_filter is not None:
            query = query.where(abac_filter)

        if limit is not None:
            query = query.limit(limit)
        if offset is not None:
            query = query.offset(offset)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_by_data_source_with_search(
        self,
        data_source_id: int,
        query: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        abac_filter=None,
    ) -> list[AssetMetadata]:
        """List assets for a data source with optional search filter.

        Args:
            data_source_id: Data source ID
            query: Optional search query (ILIKE-based substring match)
            limit: Maximum number of assets to return
            offset: Number of assets to skip
            abac_filter: Optional ABAC filter clause

        Returns:
            List of AssetMetadata DB models
        """
        filters = [AssetMetadata.data_source_id == data_source_id]

        if query:
            normalized_query = query.strip()
            if normalized_query:
                description_expr = func.coalesce(
                    AssetMetadata.meta_override["description"].cast(String),
                    AssetMetadata.meta["description"].cast(String),
                )
                filters.append(
                    or_(
                        AssetMetadata.asset_name.ilike(f"%{normalized_query}%"),
                        description_expr.ilike(f"%{normalized_query}%"),
                    )
                )

        if abac_filter is not None:
            filters.append(abac_filter)

        stmt = (
            select(AssetMetadata)
            .where(*filters)
            .order_by(AssetMetadata.created_at.desc())
            .options(selectinload(AssetMetadata.owner_user))
        )

        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_data_source(self, data_source_id: int, abac_filter=None) -> int:
        """Count assets for a data source.

        Args:
            data_source_id: Data source ID

        Returns:
            Number of assets in the data source
        """
        stmt = select(func.count()).select_from(AssetMetadata).where(AssetMetadata.data_source_id == data_source_id)
        if abac_filter is not None:
            stmt = stmt.where(abac_filter)
        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def count_by_tenant(self, tenant_id: int) -> int:
        """Count assets for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Number of assets for the tenant
        """
        result = await self.db.execute(
            select(func.count())
            .select_from(AssetMetadata)
            .join(DataSource, AssetMetadata.data_source_id == DataSource.id)
            .where(DataSource.tenant_id == tenant_id)
        )
        return int(result.scalar_one() or 0)

    async def count_by_data_source_with_query(self, data_source_id: int, query: str, abac_filter=None) -> int:
        """Count assets for a data source with key-based filter.

        Args:
            data_source_id: Data source ID
            query: Search query (ILIKE-based substring match)

        Returns:
            Number of assets matching the query
        """
        normalized_query = query.strip()
        description_expr = func.coalesce(
            AssetMetadata.meta_override["description"].cast(String),
            AssetMetadata.meta["description"].cast(String),
        )
        stmt = (
            select(func.count())
            .select_from(AssetMetadata)
            .where(
                AssetMetadata.data_source_id == data_source_id,
                or_(
                    AssetMetadata.asset_name.ilike(f"%{normalized_query}%"),
                    description_expr.ilike(f"%{normalized_query}%"),
                ),
            )
        )

        if abac_filter is not None:
            stmt = stmt.where(abac_filter)
        result = await self.db.execute(stmt)
        return int(result.scalar_one() or 0)

    async def list_by_ids(
        self,
        asset_ids: list[int],
        tenant_id: int,
        abac_filter=None,
    ) -> list[AssetMetadata]:
        """Fetch multiple assets by their IDs for a specific tenant.

        Args:
            asset_ids: List of asset IDs to fetch
            tenant_id: Tenant ID for isolation

        Returns:
            List of AssetMetadata DB models (only those that exist and belong to tenant)
        """
        if not asset_ids:
            return []

        stmt = (
            select(AssetMetadata)
            .join(DataSource, AssetMetadata.data_source_id == DataSource.id)
            .where(
                AssetMetadata.id.in_(asset_ids),
                DataSource.tenant_id == tenant_id,
            )
            .execution_options(populate_existing=True)
        )
        if abac_filter is not None:
            stmt = stmt.where(abac_filter)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, asset: AssetMetadataDomain) -> AssetMetadata:
        """Create asset metadata from domain model (DDD pattern).

        The domain model should be created using AssetMetadataDomain.create_new()
        factory method, which handles timestamp generation.

        This method atomically increments the parent data source's asset_count.

        Args:
            asset: AssetMetadataDomain instance (not yet persisted, id=None)

        Returns:
            Persisted AssetMetadata DB model with database-generated id

        Raises:
            ValueError: If asset is already persisted (id is not None)
        """
        if asset.is_persisted():
            raise ValueError(f"Asset {asset.asset_name} is already persisted (id={asset.id}). Use update() instead.")

        from apps.shared.data_source.adapters import domain_asset_metadata_to_db_model

        db_asset = domain_asset_metadata_to_db_model(asset)
        self.db.add(db_asset)
        await self.db.flush()
        await self.db.refresh(db_asset)

        # Increment asset_count in data source (atomic operation)
        await self.db.execute(
            update(DataSource)
            .where(DataSource.id == asset.data_source_id)
            .values(asset_count=DataSource.asset_count + 1)
        )

        return db_asset

    async def delete_by_data_source_and_name(self, data_source_id: int, asset_name: str) -> bool:
        """Delete asset by data source ID and name.

        Args:
            data_source_id: Data source ID
            asset_name: Asset name

        Returns:
            True if deleted, False if not found
        """
        result = await self.db.execute(
            select(AssetMetadata).where(
                AssetMetadata.data_source_id == data_source_id,
                AssetMetadata.asset_name == asset_name,
            )
        )
        db_asset = result.scalar_one_or_none()
        if not db_asset:
            return False

        data_source_id = db_asset.data_source_id
        await self.db.delete(db_asset)
        await self.db.flush()

        # Decrement asset_count in data source
        await self.db.execute(
            update(DataSource).where(DataSource.id == data_source_id).values(asset_count=DataSource.asset_count - 1)
        )

        return True

