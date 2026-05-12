"""HITL approvals router."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.exceptions import AuthorizationError
from apps.shared.db.models import HitlApproval
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.hitl.schemas import (
    HitlApprovalActionRequest,
    HitlApprovalActionResponse,
    HitlApprovalResponse,
)
from apps.tenant_app_service.hitl.service import HitlApprovalService

router = APIRouter(prefix="/hitl", tags=["hitl"])


def _to_response(approval: HitlApproval) -> HitlApprovalResponse:
    return HitlApprovalResponse(
        proposal_id=approval.proposal_id,
        status=approval.status,
        version=approval.version,
        thread_id=approval.thread_id,
        tool_name=approval.tool_name,
        tool_args=approval.tool_args,
        risk_level=approval.risk_level,
        reason=approval.reason,
        expires_at=approval.expires_at,
        approved_by=approval.approved_by,
        approved_at=approval.approved_at,
        rejected_by=approval.rejected_by,
        rejected_at=approval.rejected_at,
        created_at=approval.created_at,
        updated_at=approval.updated_at,
    )


@router.get("/approvals/{proposal_id}", response_model=HitlApprovalResponse)
async def get_approval(
    proposal_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    service = HitlApprovalService(current_user.tenant_id, db)
    approval = await service.get_approval(proposal_id)
    if approval.requested_by != current_user.id:
        raise AuthorizationError("You are not allowed to access this HITL approval")
    return _to_response(approval)


@router.post("/approvals/{proposal_id}/approve", response_model=HitlApprovalActionResponse)
async def approve_approval(
    proposal_id: str,
    request: HitlApprovalActionRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    service = HitlApprovalService(current_user.tenant_id, db)
    current = await service.get_approval(proposal_id)
    if current.requested_by != current_user.id:
        raise AuthorizationError("You are not allowed to approve this HITL proposal")
    approval = await service.approve(
        proposal_id=proposal_id,
        version=request.version,
        user_id=current_user.id,
        comment=request.comment,
    )
    return HitlApprovalActionResponse(
        proposal_id=approval.proposal_id,
        status=approval.status,
        version=approval.version,
        needs_agent_resume=True,
    )


@router.post("/approvals/{proposal_id}/reject", response_model=HitlApprovalActionResponse)
async def reject_approval(
    proposal_id: str,
    request: HitlApprovalActionRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    service = HitlApprovalService(current_user.tenant_id, db)
    current = await service.get_approval(proposal_id)
    if current.requested_by != current_user.id:
        raise AuthorizationError("You are not allowed to reject this HITL proposal")
    result = await service.reject(
        proposal_id=proposal_id,
        version=request.version,
        user_id=current_user.id,
        comment=request.comment,
    )
    return HitlApprovalActionResponse(
        proposal_id=result.proposal_id,
        status=result.status,
        version=result.version,
        needs_agent_resume=result.needs_agent_resume,
        ack_message=result.ack_message,
    )
