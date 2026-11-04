"""Integration: in-run summary rows via ``ChatRunContextAdapter`` + compact helper."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from apps.tenant_app_service.agents.memory.agent_run_summary_service import compact_prepared_messages
from apps.tenant_app_service.chat.infrastructure.persistence.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.chat.infrastructure.persistence.agent_run_summary_repository import AgentRunSummaryRepository
from apps.tenant_app_service.chat.conversation_memory_manager import ConversationMemoryManager
from apps.tenant_app_service.chat.infrastructure.persistence.main_message_repository import MainMessageRepository
from apps.tenant_app_service.chat.agent_run_port_adapter import chat_agent_run_port_for_run

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_compact_persists_in_run_summary_row(
    pg_async_db_session, sample_tenant_user_thread, runtime_context, monkeypatch
):
    thread, tenant_id, user_id = sample_tenant_user_thread
    trigger = str(uuid4())
    session_id = str(uuid4())
    await MainMessageRepository(pg_async_db_session).insert_human(
        message_id=trigger,
        thread_id=thread.id,
        content="trigger",
    )
    run = await AgentRunRepository(pg_async_db_session).create_run(
        tenant_id=tenant_id,
        thread_id=thread.id,
        agent_id=thread.agent_id,
        trigger_message_id=trigger,
        invoke_index=0,
        session_id=session_id,
    )
    runtime_context.thread_id = thread.id
    runtime_context.session_id = session_id
    config = {
        "configurable": {
            "thread_id": thread.id,
            "runtime": runtime_context.model_dump(),
            "run_id": run.id,
            "session_id": session_id,
        }
    }
    mgr = ConversationMemoryManager(
        pg_async_db_session,
        thread.id,
        tenant_id=tenant_id,
        agent_id=thread.agent_id,
        run_id=run.id,
    )
    ai1 = AIMessage(
        id="ai-old",
        content="search",
        tool_calls=[{"id": "c1", "name": "search", "args": {}}],
    )
    tool1 = ToolMessage(id="tool-old", content="big" * 500, tool_call_id="c1")
    ai2 = AIMessage(
        id="ai-new",
        content="fetch",
        tool_calls=[{"id": "c2", "name": "fetch", "args": {}}],
    )
    tool2 = ToolMessage(id="tool-new", content="fresh", tool_call_id="c2")
    await mgr.add_messages([ai1, tool1, ai2, tool2], config)
    await pg_async_db_session.commit()

    port = chat_agent_run_port_for_run(
        tenant_id=tenant_id,
        agent_id=thread.agent_id,
        run_id=run.id,
    )

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.memory.agent_run_summary_service.count_tokens",
        lambda *args, **kwargs: 10**9,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.mini_agent.MiniAgentService.create",
        lambda db, tenant_id: AsyncMock(
            summarize_run_prefix=AsyncMock(return_value="compressed prefix"),
        ),
    )

    prepared = [HumanMessage(id=trigger, content="trigger"), ai1, tool1, ai2, tool2]
    result = await compact_prepared_messages(
        prepared,
        db=pg_async_db_session,
        tenant_id=tenant_id,
        thread_id=thread.id,
        run_id=run.id,
        tools=[],
        agent_run_port=port,
    )
    await pg_async_db_session.commit()

    assert any(
        isinstance(m, SystemMessage) and m.additional_kwargs.get("summary_type") == "agent_run_summary"
        for m in result
    )
    row = await AgentRunSummaryRepository(pg_async_db_session).get_for_run(tenant_id, run.id)
    assert row is not None
    assert row.summary_text == "compressed prefix"
    assert row.cutoff_message_id == "tool-old"
