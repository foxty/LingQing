"""Reconcile orphan runs before a new user message (HITL checkpoints stay resumable)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.chat.application.runs.thread_run_service import ThreadRunService


async def execute_reconcile_before_new_turn(
    db: AsyncSession,
    tenant_id: int,
    *,
    thread_id: str,
    agent_id: int,
) -> None:
    """Close stuck non-HITL active runs so a new turn is not blocked.

    Pending HITL proposals and ``awaiting_hitl`` runs are left intact so checkpoint
    resume remains valid after later user messages.
    """
    await ThreadRunService(db, tenant_id).reconcile_before_new_turn(thread_id, agent_id)
