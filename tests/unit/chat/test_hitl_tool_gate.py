"""Tests for ChatHitlToolGate (HITL tool gate behind AgentRunPort)."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from apps.shared.db.models import HitlApproval
from apps.tenant_app_service.agents.ports.tool_hitl import HITL_ACTION_REQUIRE_HITL, ToolHitlDecision
from apps.tenant_app_service.chat.hitl_tool_gate import ChatHitlToolGate
from apps.tenant_app_service.hitl.domain import (
    HITL_PAYLOAD_TYPE_APPROVAL_REQUEST,
    HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
    HITL_STATUS_APPROVED,
    HITL_STATUS_PENDING,
    HITL_STATUS_REJECTED,
)
from apps.tenant_app_service.hitl.service import HitlApprovalService


@pytest.fixture
def gate():
    return ChatHitlToolGate(db=AsyncMock(), tenant_id=1)


@pytest.fixture
def runtime():
    runtime = MagicMock()
    runtime.thread_id = "thread_1"
    runtime.session_id = "session_a"
    runtime.user.tenant_id = 1
    runtime.user.user_id = 99
    runtime.agent_id = -1
    return runtime


@pytest.fixture
def decision():
    return ToolHitlDecision(action=HITL_ACTION_REQUIRE_HITL, reason="test", risk_level="medium")


@pytest.mark.asyncio
async def test_gate_returns_rejection_for_rejected_approval(gate, runtime, decision):
    approval = MagicMock(spec=HitlApproval)
    approval.status = HITL_STATUS_REJECTED

    with patch.object(HitlApprovalService, "get_or_create_pending", new=AsyncMock(return_value=approval)):
        with patch.object(HitlApprovalService, "build_proposal_id", return_value="hitl_old"):
            message, proposal_id = await gate.gate_tool_call(
                runtime=runtime,
                config=RunnableConfig(configurable={"db_session": AsyncMock()}),
                tool_name="hitl_test_echo",
                tool_call_id="tc_1",
                tool_args={"text": "HITL approval flow test"},
                decision=decision,
                additional_kwargs={},
            )

    assert proposal_id == "hitl_old"
    assert isinstance(message, ToolMessage)
    assert "rejected by approver" in message.content
    assert message.additional_kwargs["hitl"]["type"] == HITL_PAYLOAD_TYPE_APPROVAL_RESULT


@pytest.mark.asyncio
async def test_gate_builds_session_scoped_proposal_id(gate, runtime, decision):
    approval = MagicMock(spec=HitlApproval)
    approval.status = HITL_STATUS_PENDING

    with patch.object(HitlApprovalService, "get_or_create_pending", new=AsyncMock(return_value=approval)):
        with patch.object(
            HitlApprovalService,
            "build_proposal_id",
            return_value="hitl_session_a",
        ) as build_id:
            _, proposal_id = await gate.gate_tool_call(
                runtime=runtime,
                config=RunnableConfig(configurable={"db_session": AsyncMock()}),
                tool_name="hitl_test_echo",
                tool_call_id="tc_1",
                tool_args={"text": "HITL approval flow test"},
                decision=decision,
                additional_kwargs={},
            )

    build_id.assert_called_once_with(
        thread_id="thread_1",
        session_id="session_a",
        tool_name="hitl_test_echo",
        tool_args={"text": "HITL approval flow test"},
    )
    assert proposal_id == "hitl_session_a"


@pytest.mark.asyncio
async def test_gate_uses_configurable_proposal_id_on_resume(gate, runtime, decision):
    approval = MagicMock(spec=HitlApproval)
    approval.status = HITL_STATUS_APPROVED

    with patch.object(HitlApprovalService, "get_or_create_pending", new=AsyncMock(return_value=approval)) as pending:
        with patch.object(HitlApprovalService, "build_proposal_id") as build_id:
            config = RunnableConfig(configurable={"hitl_proposal_id": "hitl_from_checkpoint", "db_session": AsyncMock()})
            message, proposal_id = await gate.gate_tool_call(
                runtime=runtime,
                config=config,
                tool_name="hitl_test_echo",
                tool_call_id="tc_1",
                tool_args={"text": "args may differ on resume"},
                decision=decision,
                additional_kwargs={},
            )

    build_id.assert_not_called()
    pending.assert_awaited_once()
    assert pending.await_args.kwargs["proposal_id"] == "hitl_from_checkpoint"
    assert message is None
    assert proposal_id == "hitl_from_checkpoint"


@pytest.mark.asyncio
async def test_gate_approved_returns_none_to_execute_tool(gate, runtime, decision):
    approval = MagicMock(spec=HitlApproval)
    approval.status = HITL_STATUS_APPROVED

    with patch.object(HitlApprovalService, "get_or_create_pending", new=AsyncMock(return_value=approval)):
        with patch.object(HitlApprovalService, "build_proposal_id", return_value="hitl_explicit"):
            message, proposal_id = await gate.gate_tool_call(
                runtime=runtime,
                config=RunnableConfig(configurable={"db_session": AsyncMock()}),
                tool_name="hitl_test_echo",
                tool_call_id="tc_1",
                tool_args={"text": "resume executes with same args hash"},
                decision=decision,
                additional_kwargs={},
            )

    assert message is None
    assert proposal_id == "hitl_explicit"


@pytest.mark.asyncio
async def test_new_session_proposal_id_differs_from_prior_rejected_attempt():
    args = {"text": "HITL approval flow test"}
    first = HitlApprovalService.build_proposal_id(
        thread_id="thread_1",
        session_id="session_rejected",
        tool_name="hitl_test_echo",
        tool_args=args,
    )
    second = HitlApprovalService.build_proposal_id(
        thread_id="thread_1",
        session_id=str(uuid4()),
        tool_name="hitl_test_echo",
        tool_args=args,
    )
    assert first != second


@pytest.mark.asyncio
async def test_gate_pending_returns_approval_request_payload(gate, runtime, decision):
    approval = MagicMock(spec=HitlApproval)
    approval.status = HITL_STATUS_PENDING

    with patch.object(HitlApprovalService, "get_or_create_pending", new=AsyncMock(return_value=approval)):
        with patch.object(HitlApprovalService, "build_proposal_id", return_value="hitl_pending"):
            message, proposal_id = await gate.gate_tool_call(
                runtime=runtime,
                config=RunnableConfig(configurable={"db_session": AsyncMock()}),
                tool_name="hitl_test_echo",
                tool_call_id="tc_1",
                tool_args={"text": "HITL approval flow test"},
                decision=decision,
                additional_kwargs={},
            )

    assert proposal_id == "hitl_pending"
    assert message.additional_kwargs["hitl"]["type"] == HITL_PAYLOAD_TYPE_APPROVAL_REQUEST
