"""Thin audit record helpers for tenant-app use cases."""

from __future__ import annotations

import hashlib
from typing import Any

from apps.shared.audit_event.context import AuditRequestContext
from apps.shared.audit_event.event_types import TenantAuditEventType
from apps.shared.db.session import app_db_session
from apps.shared.audit_event.payload import mask_email
from apps.shared.audit_event.recorder import (
    ACTOR_TYPE_ANONYMOUS,
    ACTOR_TYPE_USER,
    OUTCOME_FAILURE,
    OUTCOME_SUCCESS,
    TenantAuditRecorder,
)


def identifier_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def record_conflict_rejection_audit(
    *,
    tenant_id: int,
    event_type: str,
    actor_user_id: int,
    resource_type: str,
    resource_id: str | None,
    payload: dict[str, Any],
    request_context: AuditRequestContext | None = None,
) -> None:
    """Write a failure audit row in a committed side transaction (survives request rollback)."""
    async with app_db_session() as db:
        recorder = TenantAuditRecorder(
            db,
            tenant_id=tenant_id,
            request_context=request_context,
        )
        await recorder.record(
            event_type=event_type,
            outcome=OUTCOME_FAILURE,
            actor_user_id=actor_user_id,
            actor_type=ACTOR_TYPE_USER,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=payload,
        )


async def record_auth_login_success(
    recorder: TenantAuditRecorder,
    *,
    user_id: int,
    auth_method: str = "password",
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.AUTH_LOGIN_SUCCESS.value,
        outcome=OUTCOME_SUCCESS,
        actor_user_id=user_id,
        actor_type=ACTOR_TYPE_USER,
        resource_type="user",
        resource_id=str(user_id),
        payload={"auth_method": auth_method},
    )


async def record_auth_login_failure(
    recorder: TenantAuditRecorder,
    *,
    attempted_identifier: str,
    failure_reason: str,
    tenant_id: int,
) -> None:
    await recorder.record(
        event_type=TenantAuditEventType.AUTH_LOGIN_FAILURE.value,
        outcome=OUTCOME_FAILURE,
        actor_user_id=None,
        actor_type=ACTOR_TYPE_ANONYMOUS,
        payload={
            "failure_reason": failure_reason,
            "attempted_identifier_hash": identifier_hash(f"{attempted_identifier}@{tenant_id}"),
        },
    )