"""Tests for read-time HITL history hydration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from apps.tenant_app_service.hitl.domain import HITL_STATUS_EXPIRED, HITL_STATUS_PENDING, HITL_STATUS_REJECTED
from apps.tenant_app_service.hitl.history import (
    build_hitl_hydrated_tool_content,
    hydrate_hitl_history_messages,
    is_hitl_proposal_blocking,
)
from apps.tenant_app_service.hitl.utils import build_hitl_gate_tool_content


def test_build_hitl_hydrated_tool_content_for_terminal_states():
    assert "expired" in build_hitl_hydrated_tool_content(HITL_STATUS_EXPIRED, "hitl_test_echo")
    assert "rejected" in build_hitl_hydrated_tool_content(HITL_STATUS_REJECTED, "hitl_test_echo")


@pytest.mark.asyncio
async def test_hydrate_hitl_history_messages_rewrites_expired_placeholder():
    pending_tool = ToolMessage(
        content="Tool 'hitl_test_echo' is pending human approval.",
        tool_call_id="tc1",
        additional_kwargs={
            "hitl": {"type": "approval_request", "proposal_id": "hitl_abc"},
            "tool_name": "hitl_test_echo",
        },
    )
    approval = MagicMock(
        proposal_id="hitl_abc",
        status=HITL_STATUS_EXPIRED,
        tool_name="hitl_test_echo",
    )

    with patch("apps.tenant_app_service.hitl.service.HitlApprovalService") as svc_cls:
        svc_cls.return_value.get_approval = AsyncMock(return_value=approval)
        hydrated = await hydrate_hitl_history_messages(
            [HumanMessage(content="hi"), pending_tool],
            tenant_id=1,
            db=AsyncMock(),
        )

    assert len(hydrated) == 2
    tool = hydrated[1]
    assert isinstance(tool, ToolMessage)
    assert tool.additional_kwargs["hitl"]["type"] == "approval_result"
    assert "expired" in tool.content


@pytest.mark.asyncio
async def test_hydrate_hitl_history_messages_normalizes_pending_content():
    pending_tool = ToolMessage(
        content="Tool 'hitl_test_echo' is pending human approval.",
        tool_call_id="tc1",
        additional_kwargs={
            "hitl": {"type": "approval_request", "proposal_id": "hitl_abc"},
            "tool_name": "hitl_test_echo",
        },
    )
    approval = MagicMock(
        proposal_id="hitl_abc",
        status=HITL_STATUS_PENDING,
        tool_name="hitl_test_echo",
    )

    with patch("apps.tenant_app_service.hitl.service.HitlApprovalService") as svc_cls:
        svc_cls.return_value.get_approval = AsyncMock(return_value=approval)
        hydrated = await hydrate_hitl_history_messages(
            [pending_tool],
            tenant_id=1,
            db=AsyncMock(),
        )

    assert hydrated[0].content == build_hitl_gate_tool_content("hitl_test_echo")


@pytest.mark.asyncio
async def test_is_hitl_proposal_blocking_false_for_expired():
    approval = MagicMock(status=HITL_STATUS_EXPIRED)

    with patch("apps.tenant_app_service.hitl.service.HitlApprovalService") as svc_cls:
        svc_cls.return_value.get_approval = AsyncMock(return_value=approval)
        blocking = await is_hitl_proposal_blocking("hitl_abc", tenant_id=1, db=AsyncMock())

    assert blocking is False
