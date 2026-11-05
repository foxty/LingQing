"""Shared Slack → ThreadRunService cancel (text command and Block Kit Stop)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.chat.application.runs.cancel_flow import execute_cancel_agent_run
from apps.tenant_app_service.chat.thread_run_service import ThreadRunService


async def cancel_slack_thread_run(
    db: AsyncSession,
    *,
    tenant_id: int,
    user_id: int,
    thread_id: str,
    run_id: str,
) -> None:
    """Cancel run (ownership enforced in ``execute_cancel_agent_run``)."""
    await execute_cancel_agent_run(
        db,
        tenant_id,
        thread_id=thread_id,
        run_id=run_id,
        user_id=user_id,
    )


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
