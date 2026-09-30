"""Scheduled worker for external document sync connectors."""

from __future__ import annotations

from apps.config import get_file_storage
from apps.shared.db.session import app_db_session
from apps.shared.document.sync_repository import DocumentSyncRepository
from apps.shared.document.sync_service import DocumentSyncService
from apps.shared.tasks.domain import TaskExecutionContext
from apps.shared.tasks.system.handler_result import SystemTaskHandlerResult, system_task_success
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


async def run_document_sync_jobs(*, task_context: TaskExecutionContext) -> SystemTaskHandlerResult:
    """Sync all active Drive connectors for one tenant."""
    tenant_id: int = task_context["tenant_id"]
    file_storage = get_file_storage()

    async with app_db_session() as session:
        sync_repo = DocumentSyncRepository(session)
        purged = await sync_repo.purge_expired_oauth_states(tenant_id=tenant_id)
        connectors = await sync_repo.list_active_connectors(tenant_id)
        await session.commit()

    results = []
    for connector in connectors:
        async with app_db_session() as session:
            service = DocumentSyncService(tenant_id, session, file_storage)
            try:
                result = await service.sync_connector(connector_id=connector.id, skip_if_locked=True)
                if result is not None:
                    results.append(result)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.warning(
                    "document_sync_worker_connector_failed tenant_id=%s connector_id=%s error=%s",
                    tenant_id,
                    connector.id,
                    exc,
                )

    added = sum(item.added for item in results)
    updated = sum(item.updated for item in results)
    deleted = sum(item.deleted for item in results)
    skipped = sum(item.skipped for item in results)
    message = (
        f"Document sync worker connectors={len(results)} purged_oauth={purged} "
        f"added={added} updated={updated} deleted={deleted} skipped={skipped}"
    )
    details = {
        "connectors": len(results),
        "purged_oauth_states": purged,
        "added": added,
        "updated": updated,
        "deleted": deleted,
        "skipped": skipped,
        "results": [item.model_dump() for item in results],
    }
    logger.info("document_sync_worker tenant_id=%s %s", tenant_id, message)

    return system_task_success(message=message, details=details)
