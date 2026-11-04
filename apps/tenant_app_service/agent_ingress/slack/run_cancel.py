"""Shared Slack → ThreadRunService cancel (text command and Block Kit Stop)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthorizationError, ValidationError
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService
from apps.tenant_app_service.chat.thread_service import ThreadService


async def cancel_slack_thread_run(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    thread_id: str,
    run_id: str,
) -> None:
    """Cancel run after verifying the linked LingQing user owns the chat thread."""
    thread = await ThreadService(tenant_id, db).get_thread(thread_id)
    if not thread or thread.user_id != user_id:
        raise AuthorizationError("You do not have permission to stop this agent run")

    await ThreadRunService(db, tenant_id).cancel_agent_run(thread_id=thread_id, run_id=run_id)


async def cancel_slack_thread_run_by_run_id(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    run_id: str,
) -> str:
    """Resolve thread from run row, cancel, return thread_id."""
    run = await ThreadRunService(db, tenant_id).get_run(run_id)
    if not run:
        raise ValidationError("Agent run not found", details={"code": "RUN_NOT_FOUND", "run_id": run_id})

    await cancel_slack_thread_run(
        db,
        tenant_id=tenant_id,
        user_id=user_id,
        thread_id=run.thread_id,
        run_id=run_id,
    )
    return run.thread_id
