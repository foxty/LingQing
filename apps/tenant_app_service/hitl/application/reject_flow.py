"""HITL reject orchestration: proposal state + chat run closure."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.tenant_app_service.chat.application.runs.closure import TerminalHitlRejectInput
from apps.tenant_app_service.chat.application.runs.terminal_hitl_reject import finalize_terminal_hitl_reject
from apps.tenant_app_service.hitl.domain import HitlResolveResult
from apps.tenant_app_service.hitl.service import HitlApprovalService
from apps.tenant_app_service.hitl.utils import build_hitl_rejected_ai_message


async def execute_hitl_reject(
    db: AsyncSession,
    tenant_id: int,
    *,
    proposal_id: str,
    version: int,
    user_id: int,
    comment: str | None = None,
) -> HitlResolveResult:
    """Mark proposal rejected (idempotent) and close the anchored agent run in chat."""
    service = HitlApprovalService(tenant_id, db)
    approval = await service.set_rejected(
        proposal_id=proposal_id,
        version=version,
        user_id=user_id,
        comment=comment,
    )
    tool_name = approval.tool_name or "tool"
    ack_message = await finalize_terminal_hitl_reject(
        db,
        tenant_id,
        TerminalHitlRejectInput(
            proposal_id=approval.proposal_id,
            session_id=approval.session_id,
            thread_id=approval.thread_id,
            agent_id=approval.agent_id,
            requested_by=approval.requested_by,
            tool_name=approval.tool_name,
            assistant_ack_content=build_hitl_rejected_ai_message(tool_name),
        ),
    )
    return HitlApprovalService.to_resolve_result(approval, ack_message=ack_message)
