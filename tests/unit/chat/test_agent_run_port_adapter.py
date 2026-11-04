"""Unit tests for ChatAgentRunPort."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from apps.tenant_app_service.chat.agent_run_port_adapter import ChatAgentRunPort, chat_agent_run_port_for_run


def test_factory_returns_chat_agent_run_port():
    port = chat_agent_run_port_for_run(
        tenant_id=1,
        agent_id=2,
        run_id="run-1",
    )
    assert isinstance(port, ChatAgentRunPort)


@pytest.mark.asyncio
@patch("apps.tenant_app_service.chat.infrastructure.adapters.agent_run_port_adapter.ChatAgentRunLifecycle")
@patch("apps.tenant_app_service.chat.infrastructure.adapters.agent_run_port_adapter.ChatRunContextAdapter")
async def test_mark_run_awaiting_hitl_delegates_to_lifecycle(mock_context_cls, mock_lifecycle_cls):
    db = AsyncMock()
    lifecycle = AsyncMock()
    mock_lifecycle_cls.return_value = lifecycle
    mock_context_cls.return_value = AsyncMock()

    @asynccontextmanager
    async def fake_app_db_session():
        yield db

    with patch(
        "apps.tenant_app_service.chat.infrastructure.adapters.agent_run_port_adapter.app_db_session",
        fake_app_db_session,
    ):
        port = ChatAgentRunPort(tenant_id=5, agent_id=1, run_id="run-x")
        await port.mark_run_awaiting_hitl("run-x")
    lifecycle.mark_run_awaiting_hitl.assert_awaited_once_with("run-x")


@pytest.mark.asyncio
@patch("apps.tenant_app_service.chat.infrastructure.adapters.agent_run_port_adapter.ChatAgentRunLifecycle")
@patch("apps.tenant_app_service.chat.infrastructure.adapters.agent_run_port_adapter.ChatRunContextAdapter")
async def test_is_run_cancelled_delegates_to_lifecycle(mock_context_cls, mock_lifecycle_cls):
    db = AsyncMock()
    lifecycle = AsyncMock()
    lifecycle.is_run_cancelled = AsyncMock(return_value=True)
    mock_lifecycle_cls.return_value = lifecycle
    mock_context_cls.return_value = AsyncMock()

    @asynccontextmanager
    async def fake_app_db_session():
        yield db

    with patch(
        "apps.tenant_app_service.chat.infrastructure.adapters.agent_run_port_adapter.app_db_session",
        fake_app_db_session,
    ):
        port = ChatAgentRunPort(tenant_id=5, agent_id=1, run_id="run-x")
        assert await port.is_run_cancelled("run-x") is True
    lifecycle.is_run_cancelled.assert_awaited_once_with("run-x")
