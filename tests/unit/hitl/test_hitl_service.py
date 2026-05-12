"""Tests for HITL approval service."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from apps.tenant_app_service.hitl.domain import HITL_STATUS_EXPIRED, HITL_STATUS_PENDING, HITL_STATUS_REJECTED
from apps.tenant_app_service.hitl.service import HitlApprovalService
from apps.shared.core.exceptions import ValidationError


def test_build_proposal_id_scopes_by_session():
    args = {"text": "HITL approval flow test"}
    first = HitlApprovalService.build_proposal_id(
        thread_id="thread_1",
        session_id="session_a",
        tool_name="hitl_test_echo",
        tool_args=args,
    )
    second = HitlApprovalService.build_proposal_id(
        thread_id="thread_1",
        session_id="session_b",
        tool_name="hitl_test_echo",
        tool_args=args,
    )
    assert first != second


@pytest.mark.asyncio
class TestHitlApprovalService:
    async def test_get_approval_auto_expires_pending(self):
        db = AsyncMock()
        service = HitlApprovalService(tenant_id=1, db=db)

        existing = MagicMock()
        existing.status = HITL_STATUS_PENDING
        existing.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)

        service.repository = MagicMock()
        service.repository.get_by_proposal_id = AsyncMock(return_value=existing)
        service.repository.save = AsyncMock(return_value=existing)

        result = await service.get_approval("hitl_1")

        assert result is existing
        assert existing.status == HITL_STATUS_EXPIRED
        service.repository.save.assert_awaited_once_with(existing)

    async def test_get_or_create_pending_resets_expired_to_pending(self):
        db = AsyncMock()
        service = HitlApprovalService(tenant_id=1, db=db)

        existing = MagicMock()
        existing.status = HITL_STATUS_EXPIRED
        existing.version = 3

        service.repository = MagicMock()
        service.repository.get_by_proposal_id = AsyncMock(return_value=existing)
        service.repository.save = AsyncMock(return_value=existing)

        result = await service.get_or_create_pending(
            tenant_id=1,
            thread_id="thread_1",
            session_id="session_2",
            agent_id=10,
            proposal_id="hitl_1",
            tool_name="search",
            tool_args={"query": "abc"},
            risk_level="medium",
            requested_by=99,
            expires_in_seconds=900,
        )

        assert result is existing
        assert existing.status == HITL_STATUS_PENDING
        assert existing.version == 4
        assert existing.session_id == "session_2"
        assert existing.agent_id == 10
        assert existing.tool_name == "search"
        assert existing.tool_args == {"query": "abc"}
        assert existing.requested_by == 99
        assert existing.expires_at is not None
        service.repository.save.assert_awaited_once_with(existing)

    async def test_get_or_create_pending_keeps_existing_non_expired(self):
        db = AsyncMock()
        service = HitlApprovalService(tenant_id=1, db=db)

        existing = MagicMock()
        existing.status = "approved"

        service.repository = MagicMock()
        service.repository.get_by_proposal_id = AsyncMock(return_value=existing)
        service.repository.save = AsyncMock(return_value=existing)

        result = await service.get_or_create_pending(
            tenant_id=1,
            thread_id="thread_1",
            session_id="session_2",
            agent_id=10,
            proposal_id="hitl_1",
            tool_name="search",
            tool_args={"query": "abc"},
            risk_level="medium",
            requested_by=99,
            expires_in_seconds=900,
        )

        assert result is existing
        service.repository.save.assert_not_awaited()

    async def test_get_or_create_pending_reopens_existing_expired_pending(self):
        db = AsyncMock()
        service = HitlApprovalService(tenant_id=1, db=db)

        existing = MagicMock()
        existing.status = HITL_STATUS_PENDING
        existing.version = 7
        existing.expires_at = datetime.now(timezone.utc) - timedelta(seconds=5)

        service.repository = MagicMock()
        service.repository.get_by_proposal_id = AsyncMock(return_value=existing)
        service.repository.save = AsyncMock(side_effect=[existing, existing])

        result = await service.get_or_create_pending(
            tenant_id=1,
            thread_id="thread_1",
            session_id="session_2",
            agent_id=10,
            proposal_id="hitl_1",
            tool_name="search",
            tool_args={"query": "abc"},
            risk_level="medium",
            requested_by=99,
            expires_in_seconds=900,
        )

        assert result is existing
        assert existing.status == HITL_STATUS_PENDING
        assert existing.version == 8
        assert service.repository.save.await_count == 2

    async def test_reject_raises_expired_when_pending_is_overdue(self):
        db = AsyncMock()
        service = HitlApprovalService(tenant_id=1, db=db)

        existing = MagicMock()
        existing.status = HITL_STATUS_PENDING
        existing.version = 4
        existing.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)

        service.repository = MagicMock()
        service.repository.get_by_proposal_id = AsyncMock(return_value=existing)
        service.repository.save = AsyncMock(return_value=existing)

        with pytest.raises(ValidationError) as exc_info:
            await service.reject(
                proposal_id="hitl_1",
                version=4,
                user_id=100,
                comment="reject",
            )

        assert exc_info.value.details.get("status") == HITL_STATUS_EXPIRED
        assert existing.status == HITL_STATUS_EXPIRED
        service.repository.save.assert_awaited_once_with(existing)

    async def test_get_or_create_pending_keeps_rejected_when_proposal_id_reused(self):
        db = AsyncMock()
        service = HitlApprovalService(tenant_id=1, db=db)

        existing = MagicMock()
        existing.status = HITL_STATUS_REJECTED
        existing.session_id = "session_1"
        existing.version = 2

        service.repository = MagicMock()
        service.repository.get_by_proposal_id = AsyncMock(return_value=existing)
        service.repository.save = AsyncMock(return_value=existing)

        result = await service.get_or_create_pending(
            tenant_id=1,
            thread_id="thread_1",
            session_id="session_1",
            agent_id=10,
            proposal_id="hitl_1",
            tool_name="hitl_test_echo",
            tool_args={"text": "HITL approval flow test"},
            risk_level="medium",
            requested_by=99,
            expires_in_seconds=900,
        )

        assert result is existing
        assert existing.status == HITL_STATUS_REJECTED
        service.repository.save.assert_not_awaited()

    async def test_cancel_superseded_pending_for_thread(self):
        db = AsyncMock()
        service = HitlApprovalService(tenant_id=1, db=db)
        service.repository = MagicMock()
        service.repository.cancel_all_pending_by_thread = AsyncMock(return_value=2)

        cancelled = await service.cancel_superseded_pending_for_thread("thread_1")

        assert cancelled == 2
        service.repository.cancel_all_pending_by_thread.assert_awaited_once_with(
            1,
            "thread_1",
            reason="superseded_by_new_user_message",
        )
