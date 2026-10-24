"""Seed agent_runs + main timeline rows for integration tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AgentRun, ChatThread
from apps.tenant_app_service.chat.agent_run_domain import AgentRunStatus
from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.chat.main_message_repository import MainMessageRepository


async def seed_stale_running_turn(
    session: AsyncSession,
    *,
    thread_id: str,
    tenant_id: int,
    agent_id: int,
    session_id: str,
    stale_minutes: int = 20,
) -> str:
    """Main human + RUNNING run older than session stale threshold (no AI)."""
    trigger_message_id = f"{thread_id}-stale-{uuid4().hex[:6]}"
    stale_at = datetime.now(UTC) - timedelta(minutes=stale_minutes)

    await MainMessageRepository(session).insert_human(
        message_id=trigger_message_id,
        thread_id=thread_id,
        content="stale in-flight human",
        timestamp=stale_at,
    )
    run = await AgentRunRepository(session).create_run(
        tenant_id=tenant_id,
        thread_id=thread_id,
        agent_id=agent_id,
        trigger_message_id=trigger_message_id,
        invoke_index=0,
        session_id=session_id,
        status=AgentRunStatus.RUNNING,
    )
    row = await session.get(AgentRun, run.id)
    if row is not None:
        row.created_at = stale_at
        row.updated_at = stale_at
        await session.flush()
    return trigger_message_id


async def seed_completed_turn_with_promoted_ai(
    session: AsyncSession,
    *,
    tenant_id: int,
    thread_id: str,
    agent_id: int,
    session_id: str,
    human_message_id: str,
    human_content: str,
    ai_message_id: str,
    ai_content: str,
    created_at: datetime | None = None,
) -> str:
    """Human on main, completed run, promoted AI on main (typical finished turn)."""
    ts = created_at or datetime.now(UTC)
    await MainMessageRepository(session).insert_human(
        message_id=human_message_id,
        thread_id=thread_id,
        content=human_content,
        timestamp=ts,
    )
    run = await AgentRunRepository(session).create_run(
        tenant_id=tenant_id,
        thread_id=thread_id,
        agent_id=agent_id,
        trigger_message_id=human_message_id,
        invoke_index=0,
        session_id=session_id,
        status=AgentRunStatus.COMPLETED,
    )
    if created_at is not None:
        row = await session.get(AgentRun, run.id)
        if row is not None:
            row.created_at = created_at
            row.updated_at = created_at
            await session.flush()

    await MainMessageRepository(session).insert_promoted_ai(
        message_id=ai_message_id,
        thread_id=thread_id,
        content=ai_content,
        agent_id=agent_id,
        trigger_message_id=human_message_id,
        agent_run_id=run.id,
        invoke_index=0,
        session_id=session_id,
        timestamp=ts + timedelta(seconds=1),
    )
    return run.id


async def seed_session_run_with_run_messages(
    session: AsyncSession,
    *,
    tenant_id: int,
    thread: ChatThread,
    session_id: str,
    human_message_id: str,
    human_content: str,
    run_messages: list[dict[str, Any]],
    created_at: datetime | None = None,
    promote_final_ai: bool = False,
) -> str:
    """One turn: main human + agent run + optional interim/final run messages."""
    ts = created_at or datetime.now(UTC)
    await MainMessageRepository(session).insert_human(
        message_id=human_message_id,
        thread_id=thread.id,
        content=human_content,
        timestamp=ts,
    )
    run = await AgentRunRepository(session).create_run(
        tenant_id=tenant_id,
        thread_id=thread.id,
        agent_id=thread.agent_id,
        trigger_message_id=human_message_id,
        invoke_index=0,
        session_id=session_id,
        status=AgentRunStatus.COMPLETED,
    )
    if created_at is not None:
        row = await session.get(AgentRun, run.id)
        if row is not None:
            row.created_at = created_at
            row.updated_at = created_at
            await session.flush()

    from apps.shared.db.models import AgentRunMessage

    for idx, spec in enumerate(run_messages):
        msg_ts = ts + timedelta(seconds=idx + 1)
        session.add(
            AgentRunMessage(
                message_id=spec["message_id"],
                run_id=run.id,
                thread_id=thread.id,
                agent_id=thread.agent_id,
                type=spec["type"],
                content=spec["content"],
                is_summarized=spec.get("is_summarized", False),
                tool_calls=spec.get("tool_calls"),
                additional_kwargs=spec.get("additional_kwargs") or {},
                session_id=session_id,
                timestamp=msg_ts,
                created_at=msg_ts,
                message_metadata={},
            )
        )
    await session.flush()

    if promote_final_ai:
        final = next((m for m in reversed(run_messages) if m["type"] == "ai"), None)
        if final:
            await MainMessageRepository(session).insert_promoted_ai(
                message_id=final["message_id"],
                thread_id=thread.id,
                content=final["content"],
                agent_id=thread.agent_id,
                trigger_message_id=human_message_id,
                agent_run_id=run.id,
                invoke_index=0,
                session_id=session_id,
                timestamp=ts + timedelta(seconds=len(run_messages) + 1),
            )
    return run.id
