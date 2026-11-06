"""Unit tests for prepare_chat_turn concurrent admission."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from apps.shared.core.exceptions import ThreadBusyError
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.domain import AgentRunDomain, AgentRunStatus
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.tenant_app_service.chat.turn_service import ChatTurnService


@pytest.fixture
def chat_service():
    service = ChatTurnService(tenant_id=1, db=AsyncMock())
    service._resolve_agent_id = AsyncMock(return_value=-1)
    service._get_agent_graph = AsyncMock(
        return_value=(
            AsyncMock(get_name=lambda: "Agent"),
            None,
        )
    )
    service._convert_to_langchain_messages = lambda messages: messages
    service._inject_message_attachments = AsyncMock(side_effect=lambda lc_messages, **kwargs: lc_messages)
    service.get_tenant_domain = AsyncMock(
        return_value=MagicMock(config=MagicMock(to_dict=lambda: {})),
    )
    service._build_runtime_config = MagicMock(return_value={"configurable": {"thread_id": "1_10_-1_abc"}})
    service.create_thread_title_if_1st_message = AsyncMock(return_value=None)
    service._build_initial_agent_messages = lambda lc_messages, request: lc_messages
    return service


@pytest.fixture
def current_user():
    return UserDTO(
        id=10,
        username="tester",
        role="user",
        tenant_id=1,
        tenant_name="Test Tenant",
    )


@pytest.fixture
def chat_request():
    return ChatRequest(
        tenant_id=1,
        agent_id=-1,
        message=SimpleMessage(role="human", content="Hello"),
        thread_id="1_10_-1_abc",
    )


@pytest.mark.asyncio
async def test_prepare_chat_turn_raises_thread_busy(chat_service, chat_request, current_user):
    with (
        patch(
            "apps.tenant_app_service.chat.application.turn.prepare_complete.execute_reconcile_before_new_turn",
            AsyncMock(),
        ),
        patch(
            "apps.tenant_app_service.chat.application.turn.prepare_complete.guard_thread_turn_start",
            AsyncMock(side_effect=ThreadBusyError("busy", details={"code": "THREAD_BUSY"})),
        ),
        patch(
            "apps.tenant_app_service.chat.application.turn.turn_helpers.ThreadRunService.send_human_and_create_runs",
            AsyncMock(),
        ) as send_mock,
    ):
        with pytest.raises(ThreadBusyError):
            await chat_service.prepare_chat_turn(chat_request, current_user)

    send_mock.assert_not_called()


@pytest.mark.asyncio
async def test_prepare_chat_turn_reconciles_before_busy_guard(chat_service, chat_request, current_user):
    with (
        patch(
            "apps.tenant_app_service.chat.application.turn.prepare_complete.execute_reconcile_before_new_turn",
            AsyncMock(),
        ) as reconcile,
        patch(
            "apps.tenant_app_service.chat.application.turn.prepare_complete.guard_thread_turn_start",
            AsyncMock(),
        ) as guard,
        patch(
            "apps.tenant_app_service.chat.application.turn.turn_helpers.ThreadRunService.send_human_and_create_runs",
            AsyncMock(
                return_value=(
                    "human-1",
                    [
                        AgentRunDomain(
                            id="run-1",
                            tenant_id=1,
                            thread_id=chat_request.thread_id,
                            agent_id=-1,
                            trigger_message_id="human-1",
                            invoke_index=0,
                            status=AgentRunStatus.QUEUED,
                            session_id=str(uuid4()),
                            created_at=datetime.now(UTC),
                            updated_at=datetime.now(UTC),
                            completed_at=None,
                        ),
                    ],
                ),
            ),
        ),
        patch(
            "apps.tenant_app_service.chat.application.turn.turn_helpers.ThreadRunService.mark_run_running",
            AsyncMock(),
        ),
    ):
        await chat_service.prepare_chat_turn(chat_request, current_user)

    reconcile.assert_awaited_once()
    guard.assert_awaited_once()
    assert reconcile.await_args.kwargs["thread_id"] == chat_request.thread_id
    assert reconcile.await_args.kwargs["agent_id"] == -1
