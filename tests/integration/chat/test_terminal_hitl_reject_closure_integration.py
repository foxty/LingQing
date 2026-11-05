"""Integration: terminal HITL reject closure (persist ack + idempotent re-finalize)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import func, select

from apps.shared.db.models import Agent, AgentRunMessage, ThreadMainMessage
from apps.tenant_app_service.chat.application.runs.closure import TerminalHitlRejectInput
from apps.tenant_app_service.chat.application.runs.terminal_hitl_reject import finalize_terminal_hitl_reject
from apps.tenant_app_service.chat.domain import AgentRunStatus
from apps.tenant_app_service.chat.infrastructure.persistence.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.chat.infrastructure.persistence.main_message_repository import MainMessageRepository
from apps.tenant_app_service.hitl.utils import build_hitl_rejected_ai_message

pytestmark = pytest.mark.integration


async def _ensure_agent(session, *, tenant_id: int, user_id: int, agent_id: int) -> None:
    if await session.get(Agent, agent_id) is not None:
        return
    session.add(
        Agent(
            id=agent_id,
            tenant_id=tenant_id,
            owner_id=user_id,
            name="integration-agent",
            description="hitl reject closure",
            system_prompt="test",
            config={},
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_finalize_terminal_hitl_reject_persists_ack_and_closes_run(
    pg_async_db_session,
    sample_tenant_user_thread,
):
    thread, tenant_id, user_id = sample_tenant_user_thread
    session_id = f"sess-hitl-reject-{uuid4().hex[:8]}"
    tool_name = "hitl_test_echo"
    ack_content = build_hitl_rejected_ai_message(tool_name)

    await _ensure_agent(
        pg_async_db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        agent_id=thread.agent_id,
    )
    trigger_message_id = f"human-{uuid4().hex[:8]}"
    await MainMessageRepository(pg_async_db_session).insert_human(
        message_id=trigger_message_id,
        thread_id=thread.id,
        content="request before hitl pause",
    )
    run = await AgentRunRepository(pg_async_db_session).create_run(
        tenant_id=tenant_id,
        thread_id=thread.id,
        agent_id=thread.agent_id,
        trigger_message_id=trigger_message_id,
        invoke_index=0,
        session_id=session_id,
        status=AgentRunStatus.AWAITING_HITL,
    )
    await pg_async_db_session.flush()

    approval = TerminalHitlRejectInput(
        proposal_id=f"hitl_{uuid4().hex[:12]}",
        session_id=session_id,
        thread_id=thread.id,
        agent_id=thread.agent_id,
        requested_by=user_id,
        tool_name=tool_name,
        assistant_ack_content=ack_content,
    )

    returned = await finalize_terminal_hitl_reject(pg_async_db_session, tenant_id, approval)
    assert returned == ack_content

    refreshed = await AgentRunRepository(pg_async_db_session).get_run(tenant_id, run.id)
    assert refreshed is not None
    assert refreshed.status == AgentRunStatus.COMPLETED

    ai_on_run = await pg_async_db_session.scalar(
        select(func.count())
        .select_from(AgentRunMessage)
        .where(
            AgentRunMessage.run_id == run.id,
            AgentRunMessage.type == "ai",
            AgentRunMessage.content == ack_content,
        )
    )
    assert ai_on_run == 1

    promoted = await pg_async_db_session.scalar(
        select(func.count())
        .select_from(ThreadMainMessage)
        .where(
            ThreadMainMessage.thread_id == thread.id,
            ThreadMainMessage.type == "ai",
            ThreadMainMessage.content == ack_content,
        )
    )
    assert promoted == 1


@pytest.mark.asyncio
async def test_finalize_terminal_hitl_reject_skips_second_persist_when_ack_exists(
    pg_async_db_session,
    sample_tenant_user_thread,
):
    thread, tenant_id, user_id = sample_tenant_user_thread
    session_id = f"sess-hitl-idem-{uuid4().hex[:8]}"
    tool_name = "hitl_test_echo"
    ack_content = build_hitl_rejected_ai_message(tool_name)

    await _ensure_agent(
        pg_async_db_session,
        tenant_id=tenant_id,
        user_id=user_id,
        agent_id=thread.agent_id,
    )
    trigger_message_id = f"human-{uuid4().hex[:8]}"
    await MainMessageRepository(pg_async_db_session).insert_human(
        message_id=trigger_message_id,
        thread_id=thread.id,
        content="request before hitl pause",
    )
    run = await AgentRunRepository(pg_async_db_session).create_run(
        tenant_id=tenant_id,
        thread_id=thread.id,
        agent_id=thread.agent_id,
        trigger_message_id=trigger_message_id,
        invoke_index=0,
        session_id=session_id,
        status=AgentRunStatus.AWAITING_HITL,
    )
    await pg_async_db_session.flush()

    approval = TerminalHitlRejectInput(
        proposal_id=f"hitl_{uuid4().hex[:12]}",
        session_id=session_id,
        thread_id=thread.id,
        agent_id=thread.agent_id,
        requested_by=user_id,
        tool_name=tool_name,
        assistant_ack_content=ack_content,
    )

    assert await finalize_terminal_hitl_reject(pg_async_db_session, tenant_id, approval) == ack_content
    assert await finalize_terminal_hitl_reject(pg_async_db_session, tenant_id, approval) is None

    ai_on_run = await pg_async_db_session.scalar(
        select(func.count())
        .select_from(AgentRunMessage)
        .where(
            AgentRunMessage.run_id == run.id,
            AgentRunMessage.type == "ai",
        )
    )
    assert ai_on_run == 1

    refreshed = await AgentRunRepository(pg_async_db_session).get_run(tenant_id, run.id)
    assert refreshed is not None
    assert refreshed.status == AgentRunStatus.COMPLETED
