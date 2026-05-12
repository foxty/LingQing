"""Tests for HITL message utilities."""

from langchain_core.messages import ToolMessage

from apps.tenant_app_service.hitl.domain import (
    HITL_STATUS_EXPIRED,
    HITL_STATUS_PENDING,
    is_hitl_blocking_status,
)
from apps.tenant_app_service.hitl.utils import (
    HITL_SKIPPED_TOOL_CONTENT,
    build_hitl_gate_tool_content,
    get_hitl_proposal_id,
    is_hitl_skipped_sibling_message,
    is_placeholder_tool_message,
)


def test_is_placeholder_tool_message_detects_skipped_content():
    message = ToolMessage(content=HITL_SKIPPED_TOOL_CONTENT, tool_call_id="tc1")
    assert is_placeholder_tool_message(message) is True


def test_is_placeholder_tool_message_detects_approval_request():
    message = ToolMessage(
        content="pending",
        tool_call_id="tc1",
        additional_kwargs={"hitl": {"type": "approval_request", "proposal_id": "p1"}},
    )
    assert is_placeholder_tool_message(message) is True


def test_is_placeholder_tool_message_allows_real_tool_result():
    message = ToolMessage(content='{"row_count": 1}', tool_call_id="tc1")
    assert is_placeholder_tool_message(message) is False


def test_build_hitl_gate_tool_content_is_status_neutral():
    assert build_hitl_gate_tool_content("hitl_test_echo") == (
        "Tool 'hitl_test_echo' requires human approval."
    )


def test_is_hitl_blocking_status():
    assert is_hitl_blocking_status(HITL_STATUS_PENDING) is True
    assert is_hitl_blocking_status(HITL_STATUS_EXPIRED) is False


def test_get_hitl_proposal_id_from_gate_message():
    message = ToolMessage(
        content="gate",
        tool_call_id="tc1",
        additional_kwargs={"hitl": {"type": "approval_request", "proposal_id": "hitl_abc"}},
    )
    assert get_hitl_proposal_id(message) == "hitl_abc"


def test_is_hitl_skipped_sibling_message():
    message = ToolMessage(content=HITL_SKIPPED_TOOL_CONTENT, tool_call_id="tc1")
    assert is_hitl_skipped_sibling_message(message) is True
    assert get_hitl_proposal_id(message) is None
