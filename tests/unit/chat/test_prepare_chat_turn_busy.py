"""Unit tests for prepare_chat_turn concurrent admission."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.core.exceptions import ThreadBusyError
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage
from apps.tenant_app_service.chat.turn_service import ChatTurnService


@pytest.fixture
def chat_service():
    service = ChatTurnService(tenant_id=1, db=AsyncMock())
    service._resolve_agent_id = AsyncMock(return_value=-1)
    service._cancel_superseded_hitl_if_needed = AsyncMock()
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
    service._persist_incoming_human_message = AsyncMock()
    service.create_thread_title_if_1st_message = AsyncMock(return_value=None)
    service._build_initial_agent_messages = lambda lc_messages, request: lc_messages
    service._is_hitl_continuation = lambda request: False
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
    with patch(
        "apps.tenant_app_service.chat.turn_service.guard_thread_turn_start",
        AsyncMock(side_effect=ThreadBusyError("busy", details={"code": "THREAD_BUSY"})),
    ):
        with pytest.raises(ThreadBusyError):
            await chat_service.prepare_chat_turn(chat_request, current_user)

    chat_service._persist_incoming_human_message.assert_not_awaited()
