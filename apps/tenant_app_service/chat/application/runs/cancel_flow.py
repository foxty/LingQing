"""User Stop: cancel in-flight agent run (chat entry for threads and ingress)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError
from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService
from apps.tenant_app_service.chat.domain.agent_run.state import AgentRunState


async def execute_cancel_agent_run(
    db: AsyncSession,
    tenant_id: int,
    *,
    thread_id: str,
    run_id: str,
    user_id: int,
) -> AgentRunState:
    """Verify thread ownership, then cancel run (DB, session HITL pending, local registry)."""
    from apps.tenant_app_service.chat.application.threads.thread_service import ThreadService

    thread = await ThreadService(tenant_id, db).get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    if thread.user_id != user_id:
        raise AuthorizationError("Access denied")

    return await ThreadRunService(db, tenant_id).cancel_agent_run(
        thread_id=thread_id,
        run_id=run_id,
    )
