"""Asset Metadata Service - Unified asset metadata management.

This service provides a unified interface for managing asset metadata
across different data source types (managed DB, external DB, SQLite).

Key responsibilities:
- Asset metadata CRUD operations
- Automatic RAG indexing synchronization
- Batch operations with transactional guarantees
- Incremental asset selection updates

Design principles:
- Single Responsibility: Focus on asset metadata lifecycle
- Consistency: Ensure metadata and RAG index are always in sync
- Reusability: Shared by CSV import, external DB import, and temp tables
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
from sqlalchemy import select

from apps.shared.authz.authz_query_builder import evaluate_resource_action
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import AuthorizationError, InternalServiceError, ResourceNotFoundError
from apps.shared.data_source.adapters import (
    db_asset_metadata_to_domain,
    discovered_asset_to_domain,
    domain_asset_metadata_to_api,
)
from apps.shared.data_source.domain import AssetMetadataDomain
from apps.shared.data_source.repository import AssetMetadataRepository
from apps.shared.data_source.schemas import AssetMetadataResponse, DiscoveredAsset
from apps.shared.db.models import AssetMetadata, DataSource
from apps.shared.db.session import AsyncSession
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    ABAC_ACTION_WRITE,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_DATA_SOURCE,
    AbacAction,
)
from apps.shared.domain.value_objects import AssetMetaVO, AssetType
from apps.shared.infra.analytics_db import AnalyticsDBManager
from apps.shared.search.repository import ResourceIndexRepository
from apps.shared.search.schemas import ResourceIndexCreateDTO
from apps.shared.utils.logger import get_logger

if TYPE_CHECKING:
    from apps.shared.search.indexing_service import ResourceIndexService
from apps.shared.utils.pagination import PaginationRequest

logger = get_logger(__name__)


def _format_exception_message(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return f"{type(exc).__name__} (no details)"


def _resolve_batch_sync_status(*, updated_count: int, skipped_count: int, error_count: int) -> str:
    if error_count <= 0:
        return "success"
    if updated_count > 0 or skipped_count > 0:
        return "partial"
    return "failed"


class AssetMetadataService(TenantAwareService):
    """Unified asset metadata management service.

    Handles asset metadata operations and ensures automatic synchronization
    with RAG indexing system.
    """

    def __init__(
        self,
        tenant_id: int,
        db_session: AsyncSession,
    ):
        """Initialize asset metadata service.

        Args:
            tenant_id: Tenant ID
            db_session: Database session
        """
        super().__init__(tenant_id, db_session=db_session)
        self.asset_repo = AssetMetadataRepository(db_session)
        self._resource_index_service: ResourceIndexService | None = None
        self._resource_index_repo: ResourceIndexRepository | None = None

    def _get_resource_index_repo(self) -> ResourceIndexRepository:
        """Lazy-initialize ResourceIndexRepository."""
        if self._resource_index_repo is None:
            self._resource_index_repo = ResourceIndexRepository(self.db_session)
        return self._resource_index_repo

    def _get_resource_index_service(self) -> "ResourceIndexService":
        """Lazy-initialize ResourceIndexService."""
        if self._resource_index_service is None:
            from apps.shared.search.indexing_service import ResourceIndexService

            self._resource_index_service = ResourceIndexService(tenant_id=self.tenant_id, db_session=self.db_session)
        return self._resource_index_service

    async def _ensure_data_source_access_for_actor(
        self,
        *,
        data_source_id: int,
        actor: ActorContext,
        action: AbacAction,
    ) -> DataSource:
        stmt = select(DataSource).where(
            DataSource.id == data_source_id,
            DataSource.tenant_id == self.tenant_id,
        )
        data_source = (await self.db_session.execute(stmt)).scalar_one_or_none()
        if not data_source:
            raise ResourceNotFoundError(f"Data source {data_source_id} not found")

        allowed = await evaluate_resource_action(
            db_session=self.db_session,
            tenant_id=self.tenant_id,
            user_id=actor.user_id,
            user_role=actor.user_role,
            resource_type=RESOURCE_TYPE_DATA_SOURCE,
            resource_id=data_source.id,
            resource_owner_id=data_source.owner_id,
            action=action,
        )
        if not allowed:
            raise AuthorizationError("无权访问该数据源")

        return data_source

    async def create_asset(
        self,
        asset: AssetMetadataDomain,
    ) -> AssetMetadataDomain:
        logger.info(
            f"Creating asset: asset_name={asset.asset_name}, "
            f"data_source_id={asset.data_source_id}, tenant_id={self.tenant_id}"
        )
        db_asset = await self.asset_repo.create(asset)
        await self._create_asset_resource_index(db_asset)
        return db_asset_metadata_to_domain(db_asset)

    async def delete_asset(
        self,
        data_source_id: int,
        asset_name: str,
    ) -> bool:
        """Delete asset metadata and its resource index (vector cleanup handled internally)."""
        logger.info(
            f"Deleting asset: data_source_id={data_source_id}, asset_name={asset_name}, tenant_id={self.tenant_id}"
        )

        asset = await self.asset_repo.get_by_data_source_and_name(data_source_id, asset_name)
        if not asset:
            logger.warning(f"Asset not found: data_source_id={data_source_id}, asset_name={asset_name}")
            return False

        deleted = await self.asset_repo.delete_by_data_source_and_name(data_source_id, asset_name)

        if deleted:
            logger.info(f"Asset deleted: data_source_id={data_source_id}, asset_name={asset_name}")
            await self._delete_asset_resource_index(asset.id)
        else:
            logger.error(f"Failed to delete asset metadata: data_source_id={data_source_id}, asset_name={asset_name}")

        return deleted

    async def batch_create_assets(
        self,
        assets: list[AssetMetadataDomain],
    ) -> tuple[list[AssetMetadataDomain], list[dict]]:
        """Batch create assets (used for external data source import)."""
        if not assets:
            return [], []

        logger.info(f"Batch creating {len(assets)} assets, tenant_id={self.tenant_id}")

        created = []
        errors = []

        for asset in assets:
            try:
                persisted = await self.create_asset(asset=asset)
                created.append(persisted)
            except Exception as e:
                errors.append({"asset_name": asset.asset_name, "error": str(e)})
                logger.error(f"Failed to create asset {asset.asset_name}: {e}", exc_info=True)

        logger.info(f"Batch create completed: {len(created)} created, {len(errors)} failed")

        return created, errors

    async def sync_assets_selection_for_actor(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
        selected_asset_names: list[str],
        discovered_assets: list[DiscoveredAsset],
    ) -> dict:
        await self._ensure_data_source_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            action=ABAC_ACTION_WRITE,
        )
        logger.info(
            f"Syncing asset selection for data_source_id={data_source_id}: "
            f"{len(selected_asset_names)} selected, tenant_id={self.tenant_id}"
        )

        existing = await self.asset_repo.list_by_data_source(data_source_id)
        existing_names = {a.asset_name for a in existing}

        to_delete = existing_names - set(selected_asset_names)
        to_add = set(selected_asset_names) - existing_names
        kept = existing_names & set(selected_asset_names)

        logger.info(f"Asset selection diff: {len(to_delete)} to delete, {len(to_add)} to add, {len(kept)} to keep")

        deleted_count = 0
        for asset_name in to_delete:
            try:
                if await self.delete_asset(data_source_id, asset_name):
                    deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete asset {asset_name}: {e}")

        to_add_assets = [
            discovered_asset_to_domain(asset, data_source_id, owner_id=actor.user_id)
            for asset in discovered_assets
            if asset.name in to_add
        ]
        created, errors = await self.batch_create_assets(to_add_assets)

        return {
            "deleted": deleted_count,
            "created": len(created),
            "kept": len(kept),
            "errors": errors,
        }

    async def list_assets_for_actor(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
        page: int = 1,
        page_size: int = 10,
        query: str | None = None,
    ) -> tuple[list[AssetMetadataResponse], PaginationRequest]:
        """List assets for a data source with pagination."""
        logger.info(
            f"Listing assets for data_source_id={data_source_id}, page={page}, page_size={page_size}, tenant_id={self.tenant_id}"
        )

        await self._ensure_data_source_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            action=ABAC_ACTION_READ,
        )

        normalized_query = query.strip() if query else None
        if normalized_query:
            total = await self.asset_repo.count_by_data_source_with_query(
                data_source_id,
                normalized_query,
            )
        else:
            total = await self.asset_repo.count_by_data_source(
                data_source_id,
            )

        if total == 0:
            pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=0)
            return [], pagination

        pagination = PaginationRequest.with_total(page=page, page_size=page_size, total=total)

        assets = await self.asset_repo.list_by_data_source_with_search(
            data_source_id=data_source_id,
            query=normalized_query,
            limit=pagination.page_size,
            offset=pagination.offset,
        )

        # Batch fetch ResourceIndex for all assets
        asset_ids = [a.id for a in assets]
        resource_index_map = await self._get_resource_index_repo().list_by_resources(
            self.tenant_id,
            RESOURCE_TYPE_ASSET,
            asset_ids,
        )

        # Convert DB → Domain → DTO
        dto_assets = [
            domain_asset_metadata_to_api(db_asset_metadata_to_domain(asset, resource_index_map.get(asset.id)))
            for asset in assets
        ]

        return dto_assets, pagination

    async def get_asset_by_name_for_actor(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
        asset_name: str,
    ) -> AssetMetadataDomain | None:
        await self._ensure_data_source_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            action=ABAC_ACTION_READ,
        )
        asset = await self.asset_repo.get_by_data_source_and_name(data_source_id, asset_name)
        return db_asset_metadata_to_domain(asset) if asset else None

    async def get_asset_by_id_for_actor(
        self,
        *,
        actor: ActorContext,
        asset_id: int,
    ) -> tuple[AssetMetadataDomain, dict[str, Any]]:
        """Fetch asset by internal DB id and return it with its data_source info."""
        asset = await self.asset_repo.get_by_id_and_tenant(asset_id, self.tenant_id)
        if not asset:
            raise ResourceNotFoundError(f"Asset {asset_id} not found")

        data_source = await self._ensure_data_source_access_for_actor(
            data_source_id=asset.data_source_id,
            actor=actor,
            action=ABAC_ACTION_READ,
        )

        asset_domain = db_asset_metadata_to_domain(asset)
        return asset_domain, {
            "id": data_source.id,
            "name": data_source.name,
            "type": data_source.type,
        }

    async def update_asset_meta_override_for_actor(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
        asset_id: int,
        description: str | None,
        column_description: dict[str, str | None] | None,
    ) -> AssetMetadataDomain:
        await self._ensure_data_source_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            action=ABAC_ACTION_WRITE,
        )

        asset = await self.asset_repo.get_by_id(asset_id)
        if not asset or asset.data_source_id != data_source_id:
            raise ValueError(f"Asset not found: asset_id={asset_id}")

        meta_override = AssetMetaVO.from_dict(asset.meta_override)

        if description is not None:
            if description == "":
                meta_override.description = None
            else:
                meta_override.description = description

        if column_description is not None:
            current_columns = dict(meta_override.column_description or {})
            for col_name, col_value in column_description.items():
                if col_value in (None, ""):
                    current_columns.pop(col_name, None)
                else:
                    current_columns[col_name] = col_value
            meta_override.column_description = current_columns

        asset.meta_override = meta_override.to_dict()
        asset.updated_at = datetime.now(UTC)
        await self.asset_repo.update(asset)
        await self._create_asset_resource_index(asset)
        return db_asset_metadata_to_domain(asset)

    async def import_csv_as_asset_for_actor(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
        asset_name: str,
        file_name: str,
        csv_path: Path,
        db_manager,
        description: str | None = None,
    ) -> tuple[AssetMetadataDomain, int]:
        data_source = await self._ensure_data_source_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            action=ABAC_ACTION_WRITE,
        )
        if not data_source.managed:
            raise ValueError("Cannot import CSV to non-managed data source")

        logger.info(
            f"Importing CSV {csv_path} to table '{asset_name}' "
            f"in data_source_id={data_source_id}, tenant_id={self.tenant_id}"
        )

        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        df = pd.read_csv(csv_path)
        logger.info(f"CSV has {len(df)} rows and {len(df.columns)} columns")

        column_metadata = [(str(col_name), str(df[col_name].dtype)) for col_name in df.columns]

        meta = AssetMetaVO(description=description) if description else None
        asset_domain = AssetMetadataDomain.from_dataframe_schema(
            data_source_id=data_source_id,
            asset_name=asset_name,
            column_metadata=column_metadata,
            row_count=0,
            asset_type=AssetType.TABLE,
            source_info={"created_from": "csv_upload", "file_name": file_name},
            meta=meta,
            owner_id=actor.user_id,
        )

        rows_imported = await db_manager.import_csv(asset_name, csv_path, asset_domain, if_exists="replace")
        asset_domain.row_count = rows_imported
        asset = await self.create_asset(asset=asset_domain)
        logger.info(f"Successfully imported {rows_imported} rows into table '{asset_name}', asset_id={asset.id}")
        return asset, rows_imported

    async def delete_assets_for_actor(
        self,
        *,
        actor: ActorContext,
        data_source_id: int,
        asset_names: list[str] | str,
        drop_table_callback=None,
    ) -> tuple[int, list[str], dict[str, str]]:
        """Delete one or multiple data assets."""
        if isinstance(asset_names, str):
            asset_names = [asset_names]

        await self._ensure_data_source_access_for_actor(
            data_source_id=data_source_id,
            actor=actor,
            action=ABAC_ACTION_WRITE,
        )

        deleted_count = 0
        failed_assets = []
        errors = {}

        for asset_name in asset_names:
            try:
                asset = await self.asset_repo.get_by_data_source_and_name(data_source_id, asset_name)
                if not asset:
                    failed_assets.append(asset_name)
                    errors[asset_name] = "Asset not found"
                    continue

                if drop_table_callback:
                    try:
                        await drop_table_callback(asset_name)
                    except Exception as e:
                        logger.warning(f"Failed to drop table '{asset_name}': {e}")

                deleted = await self.delete_asset(
                    data_source_id=data_source_id,
                    asset_name=asset_name,
                )

                if deleted:
                    deleted_count += 1
                    logger.info(f"Deleted asset '{asset_name}' from data source {data_source_id}")
                else:
                    failed_assets.append(asset_name)
                    errors[asset_name] = "Asset not found"

            except Exception as e:
                failed_assets.append(asset_name)
                errors[asset_name] = str(e)
                logger.error(f"Failed to delete asset '{asset_name}': {e}")

        operation_type = "single" if len(asset_names) == 1 else "batch"
        logger.info(
            f"{operation_type.capitalize()} delete completed: {deleted_count} deleted, "
            f"{len(failed_assets)} failed for data source {data_source_id}"
        )
        return deleted_count, failed_assets, errors

    async def sync_asset_metadata(
        self,
        asset_id: int,
        db_manager: "AnalyticsDBManager",
        force: bool = False,
        *,
        include_row_count: bool = True,
    ) -> dict[str, Any]:
        """Sync asset metadata from external data source."""
        async with db_manager:
            return await self._sync_asset_metadata_connected(
                asset_id=asset_id,
                db_manager=db_manager,
                force=force,
                include_row_count=include_row_count,
            )

    async def _sync_asset_metadata_connected(
        self,
        asset_id: int,
        db_manager: "AnalyticsDBManager",
        force: bool = False,
        *,
        include_row_count: bool = True,
    ) -> dict[str, Any]:
        """Sync asset metadata using an already-connected db manager."""
        logger.info(f"Syncing asset metadata: asset_id={asset_id}, force={force}")

        asset = await self.asset_repo.get_by_id(asset_id)
        if not asset:
            raise ValueError(f"Asset not found: asset_id={asset_id}")

        discovered_asset = await db_manager.discover_asset(asset.asset_name, include_row_count=include_row_count)
        if not discovered_asset:
            return {
                "status": "skipped",
                "asset_id": asset_id,
                "reason": "Asset not exists in source",
                "updated": False,
            }

        if asset.owner_id is None:
            raise ValueError(f"Asset owner is required: asset_id={asset.id}")

        asset_domain = discovered_asset_to_domain(
            discovered_asset,
            data_source_id=asset.data_source_id,
            owner_id=asset.owner_id,
        )
        updated = False
        stats = {"previous_row_count": asset.row_count, "new_row_count": asset_domain.row_count}

        row_count_changed = (
            include_row_count
            and asset_domain.row_count is not None
            and asset.row_count != asset_domain.row_count
        )
        columns_changed = asset.columns != asset_domain.columns

        if force or row_count_changed or columns_changed:
            if include_row_count and asset_domain.row_count is not None:
                asset.row_count = asset_domain.row_count
            asset.columns = [col.to_dict() for col in asset_domain.columns]
            asset.meta = asset_domain.meta.to_dict()
            asset.updated_at = datetime.now(UTC)
            asset.last_metadata_synced_at = datetime.now(UTC)
            asset.last_metadata_sync_error = None

            await self.asset_repo.update(asset)
            updated = True

            logger.info(
                f"Asset metadata updated: asset_id={asset_id}, row_count: {stats['previous_row_count']} -> {discovered_asset.row_count}"
            )

            await self._create_asset_resource_index(asset)
        else:
            logger.info(f"Asset metadata unchanged: asset_id={asset_id}")

        return {
            "status": "success",
            "asset_id": asset_id,
            "updated": updated,
            "stats": stats,
        }

    async def sync_all_assets(
        self,
        db_managers: dict[int, Any],
        data_source_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Sync all assets for the tenant (or specific data sources)."""
        logger.info(f"Syncing all assets for tenant {self.tenant_id}, data_source_ids={data_source_ids}")

        if self.db_session is None:
            raise InternalServiceError("Database session is required for asset sync")

        assets = await self.asset_repo.list_sync_candidates_by_tenant(
            tenant_id=self.tenant_id,
            data_source_ids=data_source_ids,
        )

        if not assets:
            logger.info(f"No external assets to sync for tenant {self.tenant_id}")
            return {
                "status": "success",
                "tenant_id": self.tenant_id,
                "updated_count": 0,
                "skipped_count": 0,
                "error_count": 0,
            }

        updated_count = 0
        skipped_count = 0
        error_count = 0
        errors = []

        assets_by_data_source: dict[int, list[Any]] = {}
        for asset in assets:
            assets_by_data_source.setdefault(asset.data_source_id, []).append(asset)

        for data_source_id, data_source_assets in assets_by_data_source.items():
            db_manager = db_managers.get(data_source_id)
            if not db_manager:
                for asset in data_source_assets:
                    error_count += 1
                    error_message = f"DB manager not provided for data_source_id={data_source_id}"
                    errors.append({"asset_id": asset.id, "error": error_message})
                    await self._record_asset_sync_error(asset.id, error_message)
                continue

            async with db_manager:
                for asset in data_source_assets:
                    try:
                        result = await self._sync_asset_metadata_connected(
                            asset_id=asset.id,
                            db_manager=db_manager,
                            force=False,
                            include_row_count=False,
                        )
                        if result["updated"]:
                            updated_count += 1
                        else:
                            skipped_count += 1
                    except Exception as e:
                        error_count += 1
                        error_message = _format_exception_message(e)
                        errors.append({"asset_id": asset.id, "error": error_message})
                        logger.error(f"Failed to sync asset {asset.id}: {error_message}")
                        await self._record_asset_sync_error(asset.id, error_message)

        await self.db_session.commit()

        return {
            "status": _resolve_batch_sync_status(
                updated_count=updated_count,
                skipped_count=skipped_count,
                error_count=error_count,
            ),
            "tenant_id": self.tenant_id,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "errors": errors[:10] if errors else None,
        }

    async def _record_asset_sync_error(self, asset_id: int, error_message: str) -> None:
        asset = await self.asset_repo.get_by_id(asset_id)
        if not asset:
            return

        asset.last_metadata_sync_error = error_message[:500]
        asset.updated_at = datetime.now(UTC)
        await self.asset_repo.update(asset)

    async def _create_asset_resource_index(self, asset_db: AssetMetadata) -> None:
        """Create or update ResourceIndex record for an asset.

        Flow 1: Use domain method to get searchable text → save as raw_content.
        Tokenization and chunking happen in Flow 2 (sync job).
        """
        try:
            asset_domain = db_asset_metadata_to_domain(asset_db)
            resource_index_svc = self._get_resource_index_service()
            searchable_text = asset_domain.to_searchable_text()
            raw_content = {
                "text": searchable_text,
                "meta": {},
            }

            await resource_index_svc.create_or_update(
                ResourceIndexCreateDTO(
                    tenant_id=self.tenant_id,
                    resource_type=RESOURCE_TYPE_ASSET,
                    resource_id=asset_db.id,
                    owner_id=asset_db.owner_id,
                    raw_content=raw_content,
                    content_updated_at=asset_db.updated_at,
                    parent_id=asset_db.data_source_id,
                )
            )
        except Exception as exc:
            logger.warning("Failed to create resource index for asset %d: %s", asset_db.id, exc)

    async def _delete_asset_resource_index(self, asset_id: int) -> None:
        """Delete ResourceIndex record for an asset (vector cleanup handled internally by ResourceIndexService)."""
        try:
            resource_index_svc = self._get_resource_index_service()
            await resource_index_svc.delete(RESOURCE_TYPE_ASSET, asset_id)
        except Exception as exc:
            logger.warning("Failed to delete resource index for asset %d: %s", asset_id, exc)
