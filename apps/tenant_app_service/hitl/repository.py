"""Repository for HITL approvals."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db import models as db_models
from apps.tenant_app_service.hitl.domain import (
    HITL_STATUS_APPROVED,
    HITL_STATUS_CANCELLED,
    HITL_STATUS_PENDING,
)

HitlApproval = db_models.HitlApproval


class HitlApprovalRepository:
    """CRUD repository for hitl approvals."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_proposal_id(self, tenant_id: int, proposal_id: str) -> HitlApproval | None:
        stmt = select(HitlApproval).where(
            HitlApproval.tenant_id == tenant_id,
            HitlApproval.proposal_id == proposal_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def save(self, approval: HitlApproval) -> HitlApproval:
        """Persist and refresh an approval model.

        Use this for updates and simple create flows where caller wants commit semantics.
        """
        self.db.add(approval)
        await self.db.commit()
        await self.db.refresh(approval)
        return approval

    async def cancel_all_pending_by_thread(
        self,
        tenant_id: int,
        thread_id: str,
        *,
        reason: str,
    ) -> int:
        """Cancel every pending approval on a thread. Returns rows updated."""
        now = datetime.now(UTC)
        stmt = (
            update(HitlApproval)
            .where(
                HitlApproval.tenant_id == tenant_id,
                HitlApproval.thread_id == thread_id,
                HitlApproval.status == HITL_STATUS_PENDING,
            )
            .values(
                status=HITL_STATUS_CANCELLED,
                reason=reason,
                updated_at=now,
            )
        )
        result = await self.db.execute(stmt)
        await self.db.flush()
        return result.rowcount or 0

    async def get_latest_pending_by_thread(self, tenant_id: int, thread_id: str) -> HitlApproval | None:
        stmt = (
            select(HitlApproval)
            .where(
                HitlApproval.tenant_id == tenant_id,
                HitlApproval.thread_id == thread_id,
                HitlApproval.status == HITL_STATUS_PENDING,
            )
            .order_by(HitlApproval.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_approved_by_thread(self, tenant_id: int, thread_id: str) -> HitlApproval | None:
        stmt = (
            select(HitlApproval)
            .where(
                HitlApproval.tenant_id == tenant_id,
                HitlApproval.thread_id == thread_id,
                HitlApproval.status == HITL_STATUS_APPROVED,
            )
            .order_by(HitlApproval.approved_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
