"""Unit tests for ChatAgentRunPort."""

from unittest.mock import AsyncMock, patch

import pytest

from apps.tenant_app_service.chat.agent_run_port_adapter import ChatAgentRunPort, chat_agent_run_port_for_run


def test_factory_returns_chat_agent_run_port():
    port = chat_agent_run_port_for_run(
        db=AsyncMock(),
        tenant_id=1,
        agent_id=2,
        run_id="run-1",
    )
    assert isinstance(port, ChatAgentRunPort)


@pytest.mark.asyncio
@patch("apps.tenant_app_service.chat.agent_run_port_adapter.ChatAgentRunLifecycle")
@patch("apps.tenant_app_service.chat.agent_run_port_adapter.ChatRunContextAdapter")
async def test_mark_run_awaiting_hitl_delegates_to_lifecycle(mock_context_cls, mock_lifecycle_cls):
    lifecycle = AsyncMock()
    mock_lifecycle_cls.return_value = lifecycle
    mock_context_cls.return_value = AsyncMock()

    port = ChatAgentRunPort(db=AsyncMock(), tenant_id=5, agent_id=1, run_id="run-x")
    await port.mark_run_awaiting_hitl("run-x")
    lifecycle.mark_run_awaiting_hitl.assert_awaited_once_with("run-x")
