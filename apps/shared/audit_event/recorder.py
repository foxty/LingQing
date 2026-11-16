"""Fail-closed tenant audit writer."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.audit_event.context import AuditRequestContext
from apps.shared.audit_event.event_types import RESERVED_EVENT_TYPES
from apps.shared.audit_event.payload import sanitize_audit_payload
from apps.shared.audit_event.repository import AuditEventRepository

ACTOR_TYPE_USER = "user"
ACTOR_TYPE_ANONYMOUS = "anonymous"

OUTCOME_SUCCESS = "success"
OUTCOME_FAILURE = "failure"


class TenantAuditRecorder:
    """Records mandatory audit events in the current DB transaction (fail-closed)."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        tenant_id: int,
        request_context: AuditRequestContext | None = None,
    ):
        self._db = db
        self._tenant_id = tenant_id
        self._ctx = request_context or AuditRequestContext(client_ip=None, user_agent=None, request_id=None)
        self._repo = AuditEventRepository(db)

    async def record(
        self,
        *,
        event_type: str,
        outcome: str,
        actor_user_id: int | None,
        actor_type: str,
        resource_type: str | None = None,
        resource_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if event_type in RESERVED_EVENT_TYPES:
            return
        await self._repo.add_event(
            tenant_id=self._tenant_id,
            actor_user_id=actor_user_id,
            actor_type=actor_type,
            event_type=event_type,
            outcome=outcome,
            client_ip=self._ctx.client_ip,
            user_agent=self._ctx.user_agent,
            request_id=self._ctx.request_id,
            resource_type=resource_type,
            resource_id=resource_id,
            payload=sanitize_audit_payload(payload),
        )