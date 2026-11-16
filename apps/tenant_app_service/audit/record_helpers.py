"""Thin audit record helpers for tenant-app use cases."""

from __future__ import annotations

import hashlib

from apps.shared.audit_event.event_types import TenantAuditEventType
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