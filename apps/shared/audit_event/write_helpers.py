"""Shared audit write helpers (tenant-agnostic semantics, same transaction)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.audit_event.context import AuditRequestContext
from apps.shared.audit_event.event_types import TenantAuditEventType
from apps.shared.audit_event.recorder import ACTOR_TYPE_USER, OUTCOME_SUCCESS, TenantAuditRecorder


async def record_acl_share_create(
    db: AsyncSession,
    *,
    tenant_id: int,
    actor_user_id: int,
    resource_type: str,
    resource_id: int,
    shared_with_user_id: int,
    permission: str,
    request_context: AuditRequestContext | None = None,
) -> None:
    recorder = TenantAuditRecorder(db, tenant_id=tenant_id, request_context=request_context)
    await recorder.record(
        event_type=TenantAuditEventType.ACL_SHARE_CREATE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type=resource_type,
        resource_id=str(resource_id),
        payload={
            "shared_with_user_id": shared_with_user_id,
            "permission": permission,
        },
    )


async def record_acl_share_revoke(
    db: AsyncSession,
    *,
    tenant_id: int,
    actor_user_id: int,
    resource_type: str,
    resource_id: int,
    shared_with_user_id: int,
    request_context: AuditRequestContext | None = None,
) -> None:
    recorder = TenantAuditRecorder(db, tenant_id=tenant_id, request_context=request_context)
    await recorder.record(
        event_type=TenantAuditEventType.ACL_SHARE_REVOKE.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=actor_user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type=resource_type,
        resource_id=str(resource_id),
        payload={"shared_with_user_id": shared_with_user_id},
    )