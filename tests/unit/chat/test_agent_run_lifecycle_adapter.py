"""Unit tests for ChatAgentRunLifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.chat.agent_run_lifecycle import ChatAgentRunLifecycle


@pytest.mark.asyncio
async def test_mark_run_awaiting_hitl_delegates_to_thread_run_service():
    db = AsyncMock()
    lifecycle = ChatAgentRunLifecycle(db, tenant_id=5)
    mock_service = MagicMock()
    mock_service.mark_run_awaiting_hitl = AsyncMock()
    lifecycle._service = mock_service

    await lifecycle.mark_run_awaiting_hitl("run-abc")

    mock_service.mark_run_awaiting_hitl.assert_awaited_once_with("run-abc")


def test_factory_returns_lifecycle_instance():
    from apps.tenant_app_service.chat.agent_run_lifecycle import chat_agent_run_lifecycle

    with patch(
        "apps.tenant_app_service.chat.infrastructure.adapters.agent_run_lifecycle.ThreadRunService",
    ):
        adapter = chat_agent_run_lifecycle(AsyncMock(), tenant_id=1)
    assert isinstance(adapter, ChatAgentRunLifecycle)
