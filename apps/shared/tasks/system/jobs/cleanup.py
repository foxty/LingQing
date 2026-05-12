"""Background cleanup tasks for temporary resources.

This module provides scheduled tasks for cleaning up:
- Expired temporary tables in Analytics DB
- Orphaned temp table metadata
- Old chart files
"""

import time
from pathlib import Path

from sqlalchemy import select

from apps.shared.data_source import (
    AssetMetadataRepository,
    DataSourceRepository,
    DataSourceService,
    TempTableRepository,
)
from apps.shared.db.models import TempTableMetadata
from apps.shared.db.session import app_db_session
from apps.shared.tasks.domain import TaskExecutionContext
from apps.shared.tasks.system.handler_result import (
    SystemTaskHandlerResult,
    system_task_failed,
    system_task_partial,
    system_task_success,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


async def cleanup_expired_temp_tables(
    task_context: TaskExecutionContext,
) -> SystemTaskHandlerResult:
    """Cleanup expired temporary tables from Analytics DB.

    This task should be run periodically (e.g., hourly via Celery/APScheduler).
    Delegates business logic to DataSourceService.cleanup_expired_temp_tables().

    Returns:
        Dictionary with aggregated cleanup statistics across all tenants
    """
    tenant_id = task_context["tenant_id"]

    logger.info("=" * 60)
    logger.info("[START] Cleanup Expired Temp Tables | tenant_id=%s", tenant_id)
    logger.info("=" * 60)

    total_cleaned = 0
    total_errors = 0
    total_skipped = 0
    total_processed = 0

    async with app_db_session() as session:
        try:
            resolved_tenant_ids = [tenant_id]

            if not resolved_tenant_ids:
                logger.info("[SKIP] No tenants with temp tables to clean up")
                return system_task_success(cleaned=0, errors=0, skipped=0, total_processed=0)

            logger.info(
                f"[INFO] Resolved {len(resolved_tenant_ids)} tenant(s) with temp tables: {resolved_tenant_ids}"
            )

            # Initialize repositories
            ds_repo = DataSourceRepository(session)
            asset_repo = AssetMetadataRepository(session)
            temp_table_repo = TempTableRepository(session)

            # Cleanup for each tenant
            for idx, tenant_id in enumerate(resolved_tenant_ids, 1):
                logger.info(f"--- Tenant {idx}/{len(resolved_tenant_ids)} (id={tenant_id}) ---")
                try:
                    ds_service = DataSourceService(
                        tenant_id=tenant_id,
                        data_source_repo=ds_repo,
                        asset_repo=asset_repo,
                    )

                    summary = await ds_service.cleanup_expired_temp_tables(temp_table_repo)

                    total_cleaned += summary["cleaned"]
                    total_errors += summary["errors"]
                    total_skipped += summary["skipped"]
                    total_processed += summary["total_processed"]

                    logger.info(
                        f"[DONE] Temp table cleanup | tenant={tenant_id} "
                        f"cleaned={summary['cleaned']} skipped={summary['skipped']} errors={summary['errors']}"
                    )

                except Exception as e:
                    logger.error(f"[FAIL] Temp table cleanup | tenant={tenant_id} error={e}", exc_info=True)
                    total_errors += 1

            # Commit all deletions
            await session.commit()

            result_summary = {
                "cleaned": total_cleaned,
                "errors": total_errors,
                "skipped": total_skipped,
                "total_processed": total_processed,
            }

            logger.info("=" * 60)
            logger.info(
                f"[DONE] Cleanup Expired Temp Tables | cleaned={total_cleaned} "
                f"skipped={total_skipped} errors={total_errors} tenants={len(resolved_tenant_ids)}"
            )
            logger.info("=" * 60)

            if total_errors <= 0:
                return system_task_success(**result_summary)

            error_message = f"Temp table cleanup completed with {total_errors} error(s)"
            if total_cleaned > 0:
                return system_task_partial(error_message, **result_summary)
            return system_task_failed(error_message, **result_summary)

        except Exception:
            await session.rollback()
            logger.error("[FAIL] Cleanup Expired Temp Tables task failed", exc_info=True)
            raise


async def cleanup_orphaned_temp_table_metadata(
    task_context: TaskExecutionContext,
) -> dict:
    """Cleanup orphaned temp table metadata without corresponding data source.

    This is a maintenance task to remove metadata records for temp tables
    where the data source has been deleted.

    Returns:
        Dictionary with cleanup statistics
    """
    tenant_id = task_context["tenant_id"]

    logger.info("=" * 60)
    logger.info("[START] Cleanup Orphaned Temp Table Metadata | tenant_id=%s", tenant_id)
    logger.info("=" * 60)

    cleaned_count = 0

    async with app_db_session() as session:
        try:
            # Find all temp table metadata in scope
            stmt = select(TempTableMetadata)
            stmt = stmt.where(TempTableMetadata.tenant_id == tenant_id)
            result = await session.execute(stmt)
            all_temp_meta = result.scalars().all()

            if not all_temp_meta:
                logger.info("[SKIP] No temp table metadata records to check")
                return {"cleaned": 0}

            logger.info(f"[INFO] Checking {len(all_temp_meta)} temp table metadata record(s)")

            from apps.shared.db.models import DataSource

            for temp_meta in all_temp_meta:
                # Check if data source exists
                ds_result = await session.execute(select(DataSource).where(DataSource.id == temp_meta.data_source_id))
                ds_exists = ds_result.scalar_one_or_none() is not None

                if not ds_exists:
                    logger.info(
                        f"[INFO] Removing orphaned metadata: table='{temp_meta.table_name}' "
                        f"data_source={temp_meta.data_source_id} (not found)"
                    )
                    await session.delete(temp_meta)
                    cleaned_count += 1

            await session.commit()

            logger.info("=" * 60)
            logger.info(f"[DONE] Cleanup Orphaned Temp Table Metadata | removed={cleaned_count}")
            logger.info("=" * 60)

            return {"cleaned": cleaned_count}

        except Exception:
            await session.rollback()
            logger.error("[FAIL] Orphaned metadata cleanup failed", exc_info=True)
            raise


def cleanup_old_charts(
    max_age_hours: int = 24,
    *,
    task_context: TaskExecutionContext,
) -> SystemTaskHandlerResult:
    """Clean up chart files older than specified time.

    Args:
        max_age_hours: Maximum file age in hours before deletion (default: 24)
        task_context: Typed runtime context carrying tenant scope

    Returns:
        Dictionary with cleanup statistics
    """
    tenant_id = task_context["tenant_id"]
    chart_dir = Path("static/charts")
    if not chart_dir.exists():
        logger.debug("[SKIP] Chart directory does not exist, skipping cleanup")
        return system_task_success(deleted_count=0, total_size=0, errors=0, skipped=True)

    logger.info(f"[START] Cleanup Old Charts | tenant_id={tenant_id} max_age={max_age_hours}h directory={chart_dir}")

    now = time.time()
    max_age_seconds = max_age_hours * 3600
    deleted_count = 0
    total_size = 0
    errors = 0

    for file_path in chart_dir.glob("chart_*.*"):
        try:
            file_age = now - file_path.stat().st_mtime
            if file_age > max_age_seconds:
                file_size = file_path.stat().st_size
                file_path.unlink()
                deleted_count += 1
                total_size += file_size
                logger.debug(f"Deleted old chart: {file_path.name} (age: {file_age / 3600:.1f}h)")
        except Exception as e:
            logger.error(f"Error deleting chart file {file_path}: {e}")
            errors += 1

    logger.info(f"[DONE] Cleanup Old Charts | deleted={deleted_count} freed={total_size / 1024:.1f}KB errors={errors}")

    data = {
        "deleted_count": deleted_count,
        "total_size": total_size,
        "errors": errors,
    }
    if errors <= 0:
        return system_task_success(**data)

    error_message = f"Chart cleanup completed with {errors} error(s)"
    if deleted_count > 0:
        return system_task_partial(error_message, **data)
    return system_task_failed(error_message, **data)
