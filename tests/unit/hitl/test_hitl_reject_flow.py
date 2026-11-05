"""Tests for HITL reject application orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.hitl.application.reject_flow import execute_hitl_reject
from apps.tenant_app_service.hitl.domain import HITL_STATUS_REJECTED
from apps.tenant_app_service.hitl.service import HitlApprovalService
from apps.tenant_app_service.hitl.utils import build_hitl_rejected_ai_message


@pytest.mark.asyncio
async def test_execute_hitl_reject_orchestrates_state_and_finalize():
    db = AsyncMock()
    approval = MagicMock(
        proposal_id="hitl_abc",
        status=HITL_STATUS_REJECTED,
        version=2,
        session_id="anchor-session",
        thread_id="thread-1",
        agent_id=-1,
        requested_by=10,
        tool_name="hitl_test_echo",
    )

    with (
        patch("apps.tenant_app_service.hitl.application.reject_flow.HitlApprovalService") as svc_cls,
        patch(
            "apps.tenant_app_service.hitl.application.reject_flow.finalize_terminal_hitl_reject",
            AsyncMock(return_value=build_hitl_rejected_ai_message("hitl_test_echo")),
        ) as finalize,
    ):
        svc_cls.return_value.set_rejected = AsyncMock(return_value=approval)
        svc_cls.to_resolve_result = HitlApprovalService.to_resolve_result
        result = await execute_hitl_reject(
            db,
            1,
            proposal_id="hitl_abc",
            version=1,
            user_id=10,
        )

    assert result.status == HITL_STATUS_REJECTED
    assert result.ack_message == build_hitl_rejected_ai_message("hitl_test_echo")
    finalize.assert_awaited_once()
    reject_input = finalize.await_args.args[2]
    assert reject_input.assistant_ack_content == build_hitl_rejected_ai_message("hitl_test_echo")
    assert reject_input.tool_name == "hitl_test_echo"
