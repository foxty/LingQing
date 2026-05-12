"""Tests for HITL gate behavior in ToolExecutor."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig

from apps.shared.db.models import HitlApproval
from apps.tenant_app_service.agents.agent_config import AgentConfig
from apps.tenant_app_service.agents.tool_executor import ToolExecutor
from apps.tenant_app_service.hitl.domain import (
    HITL_PAYLOAD_TYPE_APPROVAL_REQUEST,
    HITL_PAYLOAD_TYPE_APPROVAL_RESULT,
    HITL_STATUS_APPROVED,
    HITL_STATUS_PENDING,
    HITL_STATUS_REJECTED,
)
from apps.tenant_app_service.hitl.service import HitlApprovalService


@pytest.fixture
def executor():
    return ToolExecutor(MagicMock(spec=AgentConfig), "test_agent")


@pytest.fixture
def runtime():
    runtime = MagicMock()
    runtime.thread_id = "thread_1"
    runtime.session_id = "session_a"
    runtime.user.tenant_id = 1
    runtime.user.user_id = 99
    runtime.agent_id = -1
    return runtime


@pytest.mark.asyncio
async def test_handle_hitl_gate_returns_rejection_for_rejected_approval(executor, runtime):
    approval = MagicMock(spec=HitlApproval)
    approval.status = HITL_STATUS_REJECTED

    approval_service = MagicMock()
    approval_service.build_proposal_id.return_value = "hitl_old"
    approval_service.get_or_create_pending = AsyncMock(return_value=approval)

    message, proposal_id = await executor._handle_hitl_gate(
        runtime=runtime,
        config=RunnableConfig(configurable={}),
        approval_service=approval_service,
        risk_level="medium",
        tool_name="hitl_test_echo",
        tool_call_id="tc_1",
        tool_args={"text": "HITL approval flow test"},
        additional_kwargs={},
    )

    assert proposal_id == "hitl_old"
    assert isinstance(message, ToolMessage)
    assert "rejected by approver" in message.content
    assert message.additional_kwargs["hitl"]["type"] == HITL_PAYLOAD_TYPE_APPROVAL_RESULT


@pytest.mark.asyncio
async def test_handle_hitl_gate_builds_session_scoped_proposal_id(executor, runtime):
    approval = MagicMock(spec=HitlApproval)
    approval.status = HITL_STATUS_PENDING

    approval_service = MagicMock()
    approval_service.build_proposal_id.return_value = "hitl_session_a"
    approval_service.get_or_create_pending = AsyncMock(return_value=approval)

    _, proposal_id = await executor._handle_hitl_gate(
        runtime=runtime,
        config=RunnableConfig(configurable={}),
        approval_service=approval_service,
        risk_level="medium",
        tool_name="hitl_test_echo",
        tool_call_id="tc_1",
        tool_args={"text": "HITL approval flow test"},
        additional_kwargs={},
    )

    approval_service.build_proposal_id.assert_called_once_with(
        thread_id="thread_1",
        session_id="session_a",
        tool_name="hitl_test_echo",
        tool_args={"text": "HITL approval flow test"},
    )
    assert proposal_id == "hitl_session_a"


@pytest.mark.asyncio
async def test_handle_hitl_gate_uses_hitl_resume_proposal_id(executor, runtime):
    approval = MagicMock(spec=HitlApproval)
    approval.status = HITL_STATUS_APPROVED

    approval_service = MagicMock()
    approval_service.get_or_create_pending = AsyncMock(return_value=approval)

    config = RunnableConfig(
        configurable={"hitl_resume": {"proposal_id": "hitl_explicit", "action": "approved"}}
    )

    message, proposal_id = await executor._handle_hitl_gate(
        runtime=runtime,
        config=config,
        approval_service=approval_service,
        risk_level="medium",
        tool_name="hitl_test_echo",
        tool_call_id="tc_1",
        tool_args={"text": "different args from resume"},
        additional_kwargs={},
    )

    approval_service.build_proposal_id.assert_not_called()
    approval_service.get_or_create_pending.assert_awaited_once()
    assert approval_service.get_or_create_pending.await_args.kwargs["proposal_id"] == "hitl_explicit"
    assert message is None
    assert proposal_id == "hitl_explicit"


@pytest.mark.asyncio
async def test_new_session_proposal_id_differs_from_prior_rejected_attempt():
    """Retest with identical args in a new session must not reuse the old proposal id."""
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
async def test_handle_hitl_gate_pending_returns_approval_request_payload(executor, runtime):
    approval = MagicMock(spec=HitlApproval)
    approval.status = HITL_STATUS_PENDING

    approval_service = MagicMock()
    approval_service.build_proposal_id.return_value = "hitl_pending"
    approval_service.get_or_create_pending = AsyncMock(return_value=approval)

    message, proposal_id = await executor._handle_hitl_gate(
        runtime=runtime,
        config=RunnableConfig(configurable={}),
        approval_service=approval_service,
        risk_level="medium",
        tool_name="hitl_test_echo",
        tool_call_id="tc_1",
        tool_args={"text": "HITL approval flow test"},
        additional_kwargs={},
    )

    assert proposal_id == "hitl_pending"
    assert message.additional_kwargs["hitl"]["type"] == HITL_PAYLOAD_TYPE_APPROVAL_REQUEST
