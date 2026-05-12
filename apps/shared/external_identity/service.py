"""Identity binding application service.

Shared orchestration for resolving an external identity to an internal
user. Consumed by channel adapters (sso/, slack/) via the IdentityBindingPort
protocol. Never imports channel modules.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.external_identity.domain import (
    STATUS_ACTIVE,
    STATUS_PENDING,
    STATUS_REJECTED,
    BindAction,
    BindDecision,
    ExistingIdentityMatch,
    ExistingUserMatch,
    ExtractedIdentity,
    IdentityBindingPort,
    IdentityBindingResult,
    decide_bind,
)
from apps.shared.external_identity.repository import ExternalIdentityRepository
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class IdentityBindingService(IdentityBindingPort):
    """Shared application service for external identity binding."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ExternalIdentityRepository(db)

    async def resolve_or_bind(
        self,
        *,
        tenant_id: int,
        identity_source_id: int,
        extracted: ExtractedIdentity,
        allowed_domains: list[str],
        policy: str,
    ) -> IdentityBindingResult:
        subject_match: ExistingIdentityMatch | None = None
        existing_identity = await self.repo.get_identity_by_subject(
            tenant_id, identity_source_id, extracted.external_subject
        )
        if existing_identity:
            subject_match = ExistingIdentityMatch(
                identity_id=existing_identity.id,
                user_id=existing_identity.user_id,
                status=existing_identity.status,
            )

        email_match: ExistingUserMatch | None = None
        if extracted.email and subject_match is None:
            members = await self.repo.count_members_by_email(tenant_id, extracted.email)
            if members:
                email_match = ExistingUserMatch(user_id=members[0].id, count=len(members))

        decision = decide_bind(
            extracted=extracted,
            allowed_domains=allowed_domains,
            subject_match=subject_match,
            email_match=email_match,
            policy=policy,
        )

        return await self._apply_decision(
            tenant_id=tenant_id,
            identity_source_id=identity_source_id,
            extracted=extracted,
            decision=decision,
        )

    async def approve_pending(
        self,
        *,
        tenant_id: int,
        identity_id: int,
        user_id: int | None = None,
    ) -> IdentityBindingResult:
        identity = await self.repo.get_identity(tenant_id, identity_id)
        if not identity:
            raise ResourceNotFoundError("Pending identity not found")
        if identity.status != STATUS_PENDING:
            raise ValidationError("Identity is not pending", {"code": "IDENTITY_NOT_PENDING"})

        resolved_user_id = user_id
        if resolved_user_id is None and identity.email:
            members = await self.repo.count_members_by_email(tenant_id, identity.email)
            if len(members) == 1:
                resolved_user_id = members[0].id

        updated = await self.repo.update_identity_status(
            tenant_id, identity_id, STATUS_ACTIVE, user_id=resolved_user_id
        )
        return IdentityBindingResult(
            action=BindAction.LOGIN,
            user_id=resolved_user_id,
            identity_id=updated.id if updated else None,
        )

    async def reject_pending(self, *, tenant_id: int, identity_id: int) -> IdentityBindingResult:
        identity = await self.repo.get_identity(tenant_id, identity_id)
        if not identity:
            raise ResourceNotFoundError("Pending identity not found")
        if identity.status != STATUS_PENDING:
            raise ValidationError("Identity is not pending", {"code": "IDENTITY_NOT_PENDING"})
        updated = await self.repo.update_identity_status(tenant_id, identity_id, STATUS_REJECTED)
        return IdentityBindingResult(
            action=BindAction.DENY,
            reason="rejected_by_admin",
            identity_id=updated.id if updated else None,
        )

    async def list_pending(self, *, tenant_id: int) -> list[IdentityBindingResult]:
        rows = await self.repo.list_pending_identities(tenant_id)
        return [
            IdentityBindingResult(
                action=BindAction.PENDING,
                identity_id=r.id,
                user_id=r.user_id,
                reason=r.status,
            )
            for r in rows
        ]

    async def get_active_binding(
        self,
        *,
        tenant_id: int,
        identity_source_id: int,
        external_subject: str,
    ) -> IdentityBindingResult | None:
        identity = await self.repo.get_identity_by_subject(
            tenant_id, identity_source_id, external_subject
        )
        if not identity or identity.status != STATUS_ACTIVE:
            return None
        return IdentityBindingResult(
            action=BindAction.LOGIN,
            user_id=identity.user_id,
            identity_id=identity.id,
        )

    async def _apply_decision(
        self,
        *,
        tenant_id: int,
        identity_source_id: int,
        extracted: ExtractedIdentity,
        decision: BindDecision,
    ) -> IdentityBindingResult:
        if decision.action == BindAction.LOGIN and decision.user_id is not None:
            existing = await self.repo.get_identity_by_subject(
                tenant_id, identity_source_id, extracted.external_subject
            )
            return IdentityBindingResult(
                action=BindAction.LOGIN,
                user_id=decision.user_id,
                identity_id=existing.id if existing else None,
            )
        if decision.action == BindAction.ATTACH and decision.user_id is not None:
            row = await self.repo.create_identity(
                tenant_id=tenant_id,
                identity_source_id=identity_source_id,
                external_subject=extracted.external_subject,
                user_id=decision.user_id,
                email=extracted.email,
                display_name=extracted.display_name,
                status=STATUS_ACTIVE,
            )
            return IdentityBindingResult(
                action=BindAction.ATTACH,
                user_id=decision.user_id,
                identity_id=row.id,
            )
        if decision.action == BindAction.JIT_CREATE:
            return IdentityBindingResult(action=BindAction.JIT_CREATE)
        if decision.action == BindAction.PENDING:
            row = await self.repo.create_identity(
                tenant_id=tenant_id,
                identity_source_id=identity_source_id,
                external_subject=extracted.external_subject,
                user_id=None,
                email=extracted.email,
                display_name=extracted.display_name,
                status=STATUS_PENDING,
            )
            return IdentityBindingResult(
                action=BindAction.PENDING,
                identity_id=row.id,
                reason=decision.reason,
            )
        logger.info(
            "Identity bind denied: tenant=%s source=%s subject=%s reason=%s",
            tenant_id,
            identity_source_id,
            extracted.external_subject,
            decision.reason,
        )
        return IdentityBindingResult(action=BindAction.DENY, reason=decision.reason)
