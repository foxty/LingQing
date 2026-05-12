"""Tenant-scoped orchestration for document parse jobs."""

from __future__ import annotations

from apps.config import EnvConfig, get_file_storage
from apps.shared.db.session import app_db_session
from apps.shared.document.processing_service import DocumentProcessingService
from apps.shared.document.types import DocumentParseWorkerResult
from apps.shared.tasks.domain import TaskExecutionContext
from apps.shared.tasks.system.handler_result import (
    SystemTaskHandlerResult,
    system_task_failed,
    system_task_partial,
    system_task_success,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


async def run_document_parse_jobs(
    *,
    task_context: TaskExecutionContext,
    batch_size: int | None = None,
) -> SystemTaskHandlerResult:
    """Process queued document parses and poll async parser jobs for one tenant."""
    tenant_id: int = task_context["tenant_id"]
    resolved_batch_size = batch_size or EnvConfig.DOCUMENT_PARSE_JOB_BATCH_SIZE

    async with app_db_session() as session:
        processing = DocumentProcessingService(tenant_id, session, get_file_storage())
        result = await processing.run_pending(
            session_factory=app_db_session,
            batch_size=resolved_batch_size,
        )

    logger.info(
        "Document parse worker tenant_id=%s queued=%s completed=%s submitted=%s failed=%s polled=%s",
        tenant_id,
        result["queued"],
        result["completed"],
        result["submitted"],
        result["failed"],
        result["polled"],
    )

    return _document_parse_handler_result(result)


def _document_parse_handler_result(result: DocumentParseWorkerResult) -> SystemTaskHandlerResult:
    succeeded = result["completed"] + result["submitted"]
    failed = result["failed"]
    message = (
        f"Document parse worker queued={result['queued']} completed={result['completed']} "
        f"submitted={result['submitted']} failed={failed}"
    )
    if failed <= 0:
        return system_task_success(message=message, details=result)
    error_message = f"Document parse worker failed for {failed} job(s)"
    if succeeded > 0:
        return system_task_partial(error_message, message=message, details=result)
    return system_task_failed(error_message, details=result)
