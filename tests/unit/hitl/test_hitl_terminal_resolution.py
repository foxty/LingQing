"""Tests for HITL reject delegating run closure to chat application."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.hitl.domain import HITL_STATUS_PENDING, HITL_STATUS_REJECTED
from apps.tenant_app_service.hitl.service import HitlApprovalService
from apps.tenant_app_service.hitl.utils import build_hitl_rejected_ai_message


def test_build_hitl_rejected_ai_message():
    assert build_hitl_rejected_ai_message("hitl_test_echo") == (
        "The 'hitl_test_echo' request was rejected. No action was taken."
    )


@pytest.mark.asyncio
async def test_reject_persists_ai_ack_without_tool_message_mutation():
    db = AsyncMock()
    service = HitlApprovalService(tenant_id=1, db=db)
    approval = MagicMock(
        proposal_id="hitl_abc",
        status=HITL_STATUS_PENDING,
        version=1,
        tool_name="hitl_test_echo",
        session_id="anchor-session",
        thread_id="thread-1",
        agent_id=-1,
        requested_by=10,
    )

    service.get_approval = AsyncMock(return_value=approval)
    service._expire_if_needed = AsyncMock(return_value=approval)
    service.repository = MagicMock()
    service.repository.save = AsyncMock(return_value=approval)

    approval.status = HITL_STATUS_REJECTED
    with patch(
        "apps.tenant_app_service.hitl.application.reject_flow.execute_hitl_reject",
        AsyncMock(
            return_value=HitlApprovalService.to_resolve_result(
                approval,
                ack_message=build_hitl_rejected_ai_message("hitl_test_echo"),
            ),
        ),
    ) as execute:
        result = await service.reject(
            proposal_id="hitl_abc",
            version=1,
            user_id=10,
        )

    assert result.status == HITL_STATUS_REJECTED
    assert result.needs_agent_resume is False
    assert result.ack_message == build_hitl_rejected_ai_message("hitl_test_echo")
    execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_reject_idempotent_when_already_rejected():
    db = AsyncMock()
    service = HitlApprovalService(tenant_id=1, db=db)
    approval = MagicMock(
        proposal_id="hitl_abc",
        status=HITL_STATUS_REJECTED,
        version=2,
        tool_name="hitl_test_echo",
        session_id="anchor-session",
        thread_id="thread-1",
        agent_id=-1,
        requested_by=10,
    )

    service.get_approval = AsyncMock(return_value=approval)

    with patch(
        "apps.tenant_app_service.hitl.application.reject_flow.execute_hitl_reject",
        AsyncMock(return_value=service.to_resolve_result(approval, ack_message=None)),
    ) as execute:
        result = await service.reject(
            proposal_id="hitl_abc",
            version=2,
            user_id=10,
        )

    assert result.status == HITL_STATUS_REJECTED
    assert result.needs_agent_resume is False
    assert result.ack_message is None
    execute.assert_awaited_once()
