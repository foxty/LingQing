"""Unit tests for ChatRunContextAdapter."""

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import HumanMessage

from apps.tenant_app_service.agents.ports.run_scope import AgentRunScope
from apps.tenant_app_service.chat.run_context_adapter import ChatRunContextAdapter


@pytest.mark.asyncio
async def test_load_prompt_context_delegates_to_conversation_memory_manager():
    adapter = ChatRunContextAdapter(
        db=AsyncMock(),
        tenant_id=1,
        agent_id=2,
        run_id="run-1",
    )
    scope = AgentRunScope(tenant_id=1, thread_id="thread-1", run_id="run-1", agent_id=2)
    expected = [HumanMessage(content="hello")]

    with patch(
        "apps.tenant_app_service.chat.infrastructure.adapters.run_context_adapter.ConversationMemoryManager",
    ) as manager_cls:
        manager = AsyncMock()
        manager.load_messages_with_summary.return_value = expected
        manager_cls.return_value = manager

        result = await adapter.load_prompt_context(scope)

    assert result == expected
    manager.load_messages_with_summary.assert_awaited_once()


@pytest.mark.asyncio
async def test_persist_run_messages_delegates_to_conversation_memory_manager():
    adapter = ChatRunContextAdapter(
        db=AsyncMock(),
        tenant_id=1,
        agent_id=2,
        run_id="run-1",
    )
    scope = AgentRunScope(tenant_id=1, thread_id="thread-1", run_id="run-1", agent_id=2)
    messages = [HumanMessage(content="save me")]
    config = {"configurable": {"runtime": {}}}

    with patch(
        "apps.tenant_app_service.chat.infrastructure.adapters.run_context_adapter.ConversationMemoryManager",
    ) as manager_cls:
        manager = AsyncMock()
        manager_cls.return_value = manager

        await adapter.persist_run_messages(scope, messages, config, deduplicate=False)

    manager.add_messages.assert_awaited_once_with(messages, config, deduplicate=False)


@pytest.mark.asyncio
async def test_get_in_run_summary_maps_repository_row():
    adapter = ChatRunContextAdapter(db=AsyncMock(), tenant_id=1, agent_id=2, run_id="run-1")
    row = type("Row", (), {"summary_text": "summary", "cutoff_message_id": "cut-1"})()
    adapter._summary_repo.get_for_run = AsyncMock(return_value=row)

    record = await adapter.get_in_run_summary(tenant_id=1, run_id="run-1")

    assert record is not None
    assert record.summary_text == "summary"
    assert record.cutoff_message_id == "cut-1"


@pytest.mark.asyncio
async def test_get_in_run_summary_returns_none_when_empty_summary():
    adapter = ChatRunContextAdapter(db=AsyncMock(), tenant_id=1, agent_id=2, run_id="run-1")
    row = type("Row", (), {"summary_text": "", "cutoff_message_id": None})()
    adapter._summary_repo.get_for_run = AsyncMock(return_value=row)

    assert await adapter.get_in_run_summary(tenant_id=1, run_id="run-1") is None


@pytest.mark.asyncio
async def test_resolve_run_message_db_id_scoped_to_run():
    adapter = ChatRunContextAdapter(db=AsyncMock(), tenant_id=1, agent_id=2, run_id="run-1")
    row = type("Row", (), {"id": 99, "run_id": "run-1"})()
    adapter._message_repo.get_message_by_message_id = AsyncMock(return_value=row)

    assert await adapter.resolve_run_message_db_id("msg-1", "run-1") == 99
    assert await adapter.resolve_run_message_db_id("msg-1", "other-run") is None
