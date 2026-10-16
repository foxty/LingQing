"""Chat request thinking_effort contract."""

from apps.tenant_app_service.chat.schemas import ChatRequest, SimpleMessage


def test_chat_request_defaults_thinking_effort_to_none():
    req = ChatRequest(
        tenant_id=1,
        agent_id=2,
        message=SimpleMessage(role="human", content="hi"),
    )
    assert req.thinking_effort == "none"
