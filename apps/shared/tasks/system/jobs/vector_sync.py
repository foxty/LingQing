"""Tenant-scoped orchestration layer for Vector DB synchronization.

This module provides a thin wrapper for scheduler-friendly tenant-scoped operations.
All business logic is delegated to ResourceIndexService.

Architecture:
- CLI/Scheduler → vector_sync_tasks (orchestration) → ResourceIndexService → Repository

Responsibilities:
- Resolve tenant scope from execution context
- Dependency injection (create service instances)
- Call single-tenant service methods
- Aggregate results from multiple tenants

Design Principles:
- Thin orchestration layer (no business logic)
- Tenant-isolated execution
- Framework-agnostic for scheduler integration
"""

from time import perf_counter
from typing import Any, Literal

from sqlalchemy import select

from apps.config import get_file_storage
from apps.shared.db.models import Tenant
from apps.shared.db.session import app_db_session
from apps.shared.domain.types import (
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_DOCUMENT,
    IndexSourceType,
)
from apps.shared.search.indexing_service import ResourceIndexService
from apps.shared.tasks.domain import TaskExecutionContext
from apps.shared.tasks.system.handler_result import (
    SystemTaskHandlerResult,
    system_task_failed,
    system_task_partial,
    system_task_success,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

# Resource type to DB query mapping for orphan detection
_RESOURCE_TYPE_MAP = {
    RESOURCE_TYPE_DOCUMENT: {
        "source_label": "documents",
    },
    RESOURCE_TYPE_ASSET: {
        "source_label": "assets",
    },
    RESOURCE_TYPE_API_CONNECTOR: {
        "source_label": "api",
    },
}


# ========== Public API (Multi-tenant Orchestration) ==========


async def sync_to_vector_db(
    *,
    task_context: TaskExecutionContext,
    source: IndexSourceType | None = None,
    mode: Literal["incremental", "full"] = "incremental",
    batch_size: int = 100,
) -> SystemTaskHandlerResult:
    """Tenant-scoped orchestration for Vector DB synchronization.

    Coordinates service layer calls for one tenant resolved from task context.
    All business logic is delegated to ResourceIndexService.

    Args:
        source: Data source to sync (document, asset, api_connector, or None for all)
        mode: Sync mode ('incremental' for repair, 'full' for rebuild)
        batch_size: Streaming batch size for memory efficiency
        task_context: Typed runtime context carrying tenant scope

    Returns:
        Aggregated sync statistics
    """
    tenant_id = task_context["tenant_id"]

    logger.info("=" * 60)
    logger.info(f"[START] Vector DB Sync | source={source} mode={mode} tenant_id={tenant_id}")
    logger.info("=" * 60)

    started_at = perf_counter()
    try:
        async with app_db_session() as session:
            tenant_result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = tenant_result.scalar_one_or_none()
            tenant_config = tenant.config if tenant else None

            file_storage = get_file_storage()
            index_service = ResourceIndexService(
                tenant_id=tenant_id,
                db_session=session,
                file_storage=file_storage,
                tenant_config=tenant_config,
            )

            if mode == "full":
                await index_service.mark_all_vectors_stale()

            result = await index_service.sync_all_pending(batch_size=batch_size)
            elapsed_seconds = round(perf_counter() - started_at, 3)
            result["elapsed_seconds"] = elapsed_seconds
            result["tenant_id"] = tenant_id
            result["mode"] = mode
            await session.commit()

            logger.info(
                f"[DONE] Vector DB Sync | tenant={tenant_id} mode={mode} "
                f"synced={result.get('total_synced', 0)} failed={result.get('total_failed', 0)} "
                f"elapsed={elapsed_seconds}s"
            )
            data = dict(result)
            total_failed = int(data.get("total_failed", 0))
            if total_failed <= 0:
                return system_task_success(**data)

            total_synced = int(data.get("total_synced", 0))
            error_message = f"Vector sync completed with {total_failed} failure(s)"
            if total_synced > 0:
                return system_task_partial(error_message, **data)
            return system_task_failed(error_message, **data)

    except Exception as e:
        elapsed_seconds = round(perf_counter() - started_at, 3)
        logger.error(f"[FAIL] Vector DB Sync | tenant={tenant_id} mode={mode} error={e}", exc_info=True)
        return system_task_failed(
            str(e),
            tenant_id=tenant_id,
            mode=mode,
            elapsed_seconds=elapsed_seconds,
        )


async def cleanup_orphaned_vectors(
    *,
    task_context: TaskExecutionContext,
    dry_run: bool = False,
) -> SystemTaskHandlerResult:
    """Tenant-scoped orchestration for orphaned vector cleanup.

    Orphaned vectors occur when:
    1. Delete operation fails on Vector DB but succeeds on primary DB
    2. Program crashes during cleanup process

    Uses resource_type + resource_id metadata to detect orphans,
    comparing vector store IDs against DB IDs for each resource type.

    Args:
        dry_run: If True, only report orphans without deleting (safety mode)
        task_context: Typed runtime context carrying tenant scope

    Returns:
        Cleanup statistics with orphan counts
    """
    tenant_id = task_context["tenant_id"]

    dry_run_tag = " [DRY RUN]" if dry_run else ""
    logger.info("=" * 60)
    logger.info(f"[START] Orphan Cleanup{dry_run_tag} | tenant_id={tenant_id}")
    logger.info("=" * 60)

    results = []
    for resource_type, config in _RESOURCE_TYPE_MAP.items():
        logger.info(f"--- Cleaning up {config['source_label']}{dry_run_tag} ---")
        result = await _cleanup_by_resource_type(tenant_id, resource_type, config["source_label"], dry_run)
        results.append(result)

    total_orphaned = sum(r["orphaned_count"] for r in results)
    total_cleaned = sum(r["cleaned_count"] for r in results)
    detail_errors = sum(1 for result in results if result.get("error"))

    data = {
        "total_orphaned": total_orphaned,
        "total_cleaned": total_cleaned,
        "dry_run": dry_run,
        "details": results,
    }

    logger.info("=" * 60)
    if dry_run:
        logger.info(f"[DONE] Orphan Cleanup [DRY RUN] | found={total_orphaned} orphaned vectors")
    else:
        logger.info(f"[DONE] Orphan Cleanup | cleaned={total_cleaned}/{total_orphaned} orphaned vectors")
    logger.info("=" * 60)

    if detail_errors <= 0:
        return system_task_success(**data)

    error_message = f"Orphan cleanup completed with {detail_errors} error(s)"
    if total_cleaned > 0 or dry_run:
        return system_task_partial(error_message, **data)
    return system_task_failed(error_message, **data)


# ========== Orphan Cleanup Operations ==========


async def _cleanup_by_resource_type(
    tenant_id: int,
    resource_type: str,
    source_label: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Cleanup orphaned vectors for a single resource type via ResourceIndexService."""
    dry_run_tag = " [DRY RUN]" if dry_run else ""
    logger.info(f"[START] {source_label} orphan cleanup{dry_run_tag} | tenant={tenant_id}")
    try:
        async with app_db_session() as session:
            tenant_result = await session.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = tenant_result.scalar_one_or_none()
            tenant_config = tenant.config if tenant else None

            index_service = ResourceIndexService(tenant_id=tenant_id, db_session=session, tenant_config=tenant_config)
            result = await index_service.cleanup_orphan_vectors(resource_type, dry_run=dry_run)

            if result["orphaned_count"] == 0:
                logger.info(f"No orphaned {source_label} vectors found for tenant {tenant_id}")

            return {
                "tenant_id": tenant_id,
                "source_type": source_label,
                "resource_type": resource_type,
                "orphaned_count": result["orphaned_count"],
                "cleaned_count": result["cleaned_count"],
                "orphaned_ids": result.get("orphaned_ids", []),
            }

    except Exception as e:
        logger.error(f"[FAIL] {source_label} orphan cleanup | tenant={tenant_id} error={e}", exc_info=True)
        return {
            "tenant_id": tenant_id,
            "source_type": source_label,
            "resource_type": resource_type,
            "orphaned_count": 0,
            "cleaned_count": 0,
            "error": str(e),
        }
