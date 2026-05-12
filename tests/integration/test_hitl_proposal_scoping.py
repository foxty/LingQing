"""Integration tests for session-scoped HITL proposal identity."""

from uuid import uuid4

import pytest

from apps.tenant_app_service.hitl.domain import HITL_STATUS_APPROVED, HITL_STATUS_PENDING, HITL_STATUS_REJECTED
from apps.tenant_app_service.hitl.service import HitlApprovalService


@pytest.mark.asyncio
async def test_retest_same_args_new_session_gets_fresh_pending(pg_async_db_session, sample_tenant_user_thread):
    """A retest in a new session must not inherit a rejected approval from an earlier session."""
    thread, tenant_id, user_id = sample_tenant_user_thread
    service = HitlApprovalService(tenant_id, pg_async_db_session)
    tool_args = {"text": "HITL approval flow test"}

    session_rejected = str(uuid4())
    proposal_rejected = HitlApprovalService.build_proposal_id(
        thread_id=thread.id,
        session_id=session_rejected,
        tool_name="hitl_test_echo",
        tool_args=tool_args,
    )

    created = await service.get_or_create_pending(
        tenant_id=tenant_id,
        thread_id=thread.id,
        session_id=session_rejected,
        agent_id=thread.agent_id,
        proposal_id=proposal_rejected,
        tool_name="hitl_test_echo",
        tool_args=tool_args,
        risk_level="medium",
        requested_by=user_id,
    )
    await service.reject(proposal_id=proposal_rejected, version=created.version, user_id=user_id)

    session_retest = str(uuid4())
    proposal_retest = HitlApprovalService.build_proposal_id(
        thread_id=thread.id,
        session_id=session_retest,
        tool_name="hitl_test_echo",
        tool_args=tool_args,
    )
    assert proposal_retest != proposal_rejected

    retest = await service.get_or_create_pending(
        tenant_id=tenant_id,
        thread_id=thread.id,
        session_id=session_retest,
        agent_id=thread.agent_id,
        proposal_id=proposal_retest,
        tool_name="hitl_test_echo",
        tool_args=tool_args,
        risk_level="medium",
        requested_by=user_id,
    )

    assert retest.proposal_id == proposal_retest
    assert retest.status == HITL_STATUS_PENDING
    assert retest.session_id == session_retest

    prior = await service.get_approval(proposal_rejected)
    assert prior.status == HITL_STATUS_REJECTED


@pytest.mark.asyncio
async def test_approve_new_session_after_prior_reject_same_tool_args(
    pg_async_db_session, sample_tenant_user_thread
):
    """Approving must not collide with a prior session's version on the same thread/tool/args."""
    thread, tenant_id, user_id = sample_tenant_user_thread
    service = HitlApprovalService(tenant_id, pg_async_db_session)
    tool_args = {"text": "HITL approval flow test"}

    session_rejected = str(uuid4())
    proposal_rejected = HitlApprovalService.build_proposal_id(
        thread_id=thread.id,
        session_id=session_rejected,
        tool_name="hitl_test_echo",
        tool_args=tool_args,
    )
    rejected = await service.get_or_create_pending(
        tenant_id=tenant_id,
        thread_id=thread.id,
        session_id=session_rejected,
        agent_id=thread.agent_id,
        proposal_id=proposal_rejected,
        tool_name="hitl_test_echo",
        tool_args=tool_args,
        risk_level="medium",
        requested_by=user_id,
    )
    await service.reject(proposal_id=proposal_rejected, version=rejected.version, user_id=user_id)

    session_approve = str(uuid4())
    proposal_approve = HitlApprovalService.build_proposal_id(
        thread_id=thread.id,
        session_id=session_approve,
        tool_name="hitl_test_echo",
        tool_args=tool_args,
    )
    pending = await service.get_or_create_pending(
        tenant_id=tenant_id,
        thread_id=thread.id,
        session_id=session_approve,
        agent_id=thread.agent_id,
        proposal_id=proposal_approve,
        tool_name="hitl_test_echo",
        tool_args=tool_args,
        risk_level="medium",
        requested_by=user_id,
    )

    pending_version = pending.version
    approved = await service.approve(
        proposal_id=proposal_approve,
        version=pending_version,
        user_id=user_id,
    )

    assert approved.status == HITL_STATUS_APPROVED
    assert approved.version == pending_version + 1
