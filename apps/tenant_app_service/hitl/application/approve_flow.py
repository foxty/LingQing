"""HITL approve orchestration (proposal state only; resume is separate SSE)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import HitlApproval
from apps.tenant_app_service.hitl.service import HitlApprovalService


async def execute_hitl_approve(
    db: AsyncSession,
    tenant_id: int,
    *,
    proposal_id: str,
    version: int,
    user_id: int,
    comment: str | None = None,
) -> HitlApproval:
    """Persist approved proposal; caller must authorize before invoking."""
    service = HitlApprovalService(tenant_id, db)
    return await service.approve(
        proposal_id=proposal_id,
        version=version,
        user_id=user_id,
        comment=comment,
    )
