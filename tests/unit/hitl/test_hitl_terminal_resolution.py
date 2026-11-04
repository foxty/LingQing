"""Tests for terminal HITL resolution (reject persists AI ack only)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.shared.core.exceptions import ValidationError
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

    run_message_repo = MagicMock()
    run_message_repo.get_messages_by_session = AsyncMock(return_value=[])
    run_domain = MagicMock(id="run-1")

    mock_run_service = MagicMock()
    mock_run_service.get_run_by_session_id = AsyncMock(return_value=run_domain)
    mock_run_service.mark_run_completed = AsyncMock()
    mock_run_service.finalize_run_for_main = AsyncMock()

    with (
        patch(
            "apps.tenant_app_service.hitl.service._agent_run_message_repository",
            return_value=run_message_repo,
        ),
        patch(
            "apps.tenant_app_service.hitl.service._thread_run_service_for_session",
            return_value=mock_run_service,
        ),
        patch(
            "apps.tenant_app_service.chat.infrastructure.adapters.agent_run_port_adapter"
            ".chat_agent_run_port_for_run",
        ) as run_port_factory,
    ):
        run_port = run_port_factory.return_value
        run_port.persist_run_messages = AsyncMock()

        result = await service.reject(
            proposal_id="hitl_abc",
            version=1,
            user_id=10,
        )

    assert result.status == HITL_STATUS_REJECTED
    assert result.needs_agent_resume is False
    assert result.ack_message == build_hitl_rejected_ai_message("hitl_test_echo")
    run_port.persist_run_messages.assert_awaited_once()
    mock_run_service.mark_run_completed.assert_awaited_once_with("run-1")
    mock_run_service.finalize_run_for_main.assert_awaited_once_with("run-1")


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
    service._finalize_terminal_resolution = AsyncMock(return_value=None)

    result = await service.reject(
        proposal_id="hitl_abc",
        version=2,
        user_id=10,
    )

    assert result.status == HITL_STATUS_REJECTED
    assert result.needs_agent_resume is False
    assert result.ack_message is None
    service._finalize_terminal_resolution.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_terminal_resolution_requires_reject_resolution():
    db = AsyncMock()
    service = HitlApprovalService(tenant_id=1, db=db)
    approval = MagicMock(status=HITL_STATUS_REJECTED)

    with pytest.raises(ValidationError):
        await service._finalize_terminal_resolution(approval, "approved")
