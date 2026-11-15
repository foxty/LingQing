"""Asset metadata sync orchestration for scheduler.

Tenant-scoped orchestration layer for asset metadata synchronization.

Architecture:
- CLI/Scheduler → asset_sync_tasks (orchestration) → AssetMetadataService (business logic)

Responsibilities (simplified):
- Resolve tenant scope from execution context
- Dependency injection (create service instances per tenant)
- Call service layer methods
- Aggregate multi-tenant results
"""

from typing import Any

from sqlalchemy import select

from apps.shared.db.models import DataSource
from apps.shared.db.session import app_db_session
from apps.shared.external_systems.data_source.asset_metadata_service import (
    AssetMetadataService,
    _format_exception_message,
)
from apps.shared.external_systems.data_source.catalog_sync import CatalogSyncCredentials
from apps.shared.external_systems.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.external_systems.data_source.service import DataSourceService
from apps.shared.external_systems.domain.types import CREDENTIAL_MODE_USER
from apps.shared.tasks.domain import TaskExecutionContext
from apps.shared.tasks.system.handler_result import (
    SystemTaskHandlerResult,
    system_task_failed,
    system_task_partial,
    system_task_success,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def _build_sync_error_message(*, total_errors: int, total_updated: int) -> str:
    if total_updated > 0:
        return f"Asset metadata sync completed with {total_errors} error(s) and {total_updated} update(s)"
    return f"Asset metadata sync failed with {total_errors} error(s)"


def _resolve_tenant_sync_status(result: dict[str, Any]) -> str:
    if result.get("status") == "error":
        return "failed"
    return result.get("status") or "success"


# ========== Public API (Multi-tenant Orchestration) ==========


async def sync_asset_metadata_for_all(
    *,
    task_context: TaskExecutionContext,
) -> SystemTaskHandlerResult:
    """Tenant-scoped orchestration for asset metadata synchronization.

    Refreshes asset metadata (schema, row_count) from external data sources.
    Delegates to AssetMetadataService.sync_all_assets() for each tenant.

    Args:
        task_context: Typed runtime context carrying tenant scope

    Returns:
        Aggregated sync statistics
    """
    tenant_id = task_context["tenant_id"]
    tenants = [tenant_id]

    logger.info("=" * 60)
    logger.info(f"[START] Asset Metadata Sync | tenant_id={tenant_id}")
    logger.info("=" * 60)

    logger.info(f"[INFO] Resolved {len(tenants)} tenant(s): {tenants}")

    # Execute sync for each tenant
    results = []
    for idx, tenant_id in enumerate(tenants, 1):
        logger.info(f"--- Tenant {idx}/{len(tenants)} (id={tenant_id}) ---")
        result = await _sync_tenant_assets(tenant_id)
        results.append(result)

    # Aggregate results
    total_updated = sum(r.get("updated_count", 0) for r in results)
    total_skipped = sum(r.get("skipped_count", 0) for r in results)
    total_errors = sum(r.get("error_count", 0) for r in results)
    success_count = sum(1 for r in results if _resolve_tenant_sync_status(r) == "success")

    data = {
        "total_tenants": len(tenants),
        "successful_operations": success_count,
        "total_updated": total_updated,
        "total_skipped": total_skipped,
        "total_errors": total_errors,
        "details": results,
    }

    logger.info("=" * 60)
    logger.info(
        f"[DONE] Asset Metadata Sync | {success_count}/{len(results)} tenants OK "
        f"| updated={total_updated} skipped={total_skipped} errors={total_errors}"
    )
    logger.info("=" * 60)

    if total_errors <= 0:
        return system_task_success(**data)

    error_message = _build_sync_error_message(total_errors=total_errors, total_updated=total_updated)
    if total_updated > 0 or total_skipped > 0:
        return system_task_partial(error_message, **data)
    return system_task_failed(error_message, **data)


async def _sync_tenant_assets(tenant_id: int) -> dict[str, Any]:
    """Sync all assets for a single tenant (delegates to AssetMetadataService).

    Creates service instance and calls sync_all_assets() method.
    """
    logger.info(f"[START] Asset metadata sync | tenant={tenant_id}")
    try:
        async with app_db_session() as session:
            # Create service instances
            asset_repo = AssetMetadataRepository(session)
            data_source_repo = DataSourceRepository(session)
            asset_service = AssetMetadataService(
                tenant_id=tenant_id,
                db_session=session,
            )

            ds_service = DataSourceService(
                tenant_id=tenant_id,
                data_source_repo=data_source_repo,
                asset_repo=asset_repo,
            )

            result = await session.execute(
                select(DataSource.id, DataSource.credential_mode, DataSource.config, DataSource.type).where(
                    DataSource.tenant_id == tenant_id,
                    DataSource.managed.is_(False),
                )
            )
            rows = result.all()
            resolved_data_source_ids: list[int] = []
            skipped_user_mode = 0
            for row in rows:
                ds_id = row[0]
                credential_mode = row[1] if len(row) > 1 else "shared"
                config = row[2] if len(row) > 2 else {}
                ds_type = row[3] if len(row) > 3 else None
                if (credential_mode or "shared") == CREDENTIAL_MODE_USER:
                    if not CatalogSyncCredentials.is_configured_in_config(config, data_source_type=ds_type):
                        skipped_user_mode += 1
                        continue
                resolved_data_source_ids.append(ds_id)
            if not resolved_data_source_ids:
                logger.info(
                    f"[SKIP] No syncable external data sources for tenant={tenant_id} "
                    f"(skipped_user_mode={skipped_user_mode})"
                )
                return {
                    "status": "success",
                    "tenant_id": tenant_id,
                    "updated_count": 0,
                    "skipped_count": skipped_user_mode,
                    "error_count": 0,
                }

            logger.info(f"[INFO] tenant={tenant_id} data_sources={resolved_data_source_ids}")

            # Create db_managers dict for all data sources
            db_managers: dict[int, Any] = {}
            for ds_id in resolved_data_source_ids:
                try:
                    row = next((r for r in rows if r[0] == ds_id), None)
                    cred_mode = (row[1] if row and len(row) > 1 else None) or "shared"
                    if cred_mode == CREDENTIAL_MODE_USER:
                        db_managers[ds_id] = await ds_service.get_db_manager_for_metadata_sync(ds_id)
                    else:
                        db_managers[ds_id] = await ds_service.get_db_manager(ds_id)
                except Exception as e:
                    reason = _format_exception_message(e)
                    logger.warning(
                        "Asset metadata sync: could not open warehouse for data_source_id=%s tenant_id=%s: %s",
                        ds_id,
                        tenant_id,
                        reason,
                        exc_info=True,
                    )

            # Delegate to service layer with db_managers
            result = await asset_service.sync_all_assets(
                db_managers=db_managers,
                data_source_ids=resolved_data_source_ids,
            )

            logger.info(
                f"[DONE] Asset metadata sync | tenant={tenant_id} "
                f"updated={result.get('updated_count', 0)} "
                f"skipped={result.get('skipped_count', 0)} "
                f"errors={result.get('error_count', 0)} "
                f"status={result.get('status', 'success')}"
            )
            return {
                "status": result.get("status", "success"),
                "tenant_id": tenant_id,
                "skipped_user_mode": skipped_user_mode,
                **result,
            }

    except Exception as e:
        logger.error(f"[FAIL] Asset metadata sync | tenant={tenant_id} error={e}", exc_info=True)
        return {
            "status": "failed",
            "tenant_id": tenant_id,
            "updated_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "error": str(e),
        }
