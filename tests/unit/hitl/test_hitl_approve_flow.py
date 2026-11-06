"""Tests for HITL approve application orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.tenant_app_service.hitl.application.approve_flow import execute_hitl_approve


@pytest.mark.asyncio
async def test_execute_hitl_approve_delegates_to_service():
    db = AsyncMock()
    approval = MagicMock(proposal_id="hitl_abc", status="approved")

    with patch("apps.tenant_app_service.hitl.application.approve_flow.HitlApprovalService") as svc_cls:
        svc_cls.return_value.approve = AsyncMock(return_value=approval)
        result = await execute_hitl_approve(
            db,
            1,
            proposal_id="hitl_abc",
            version=1,
            user_id=10,
        )

    assert result is approval
    svc_cls.return_value.approve.assert_awaited_once()
