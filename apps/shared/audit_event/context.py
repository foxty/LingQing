"""Request-scoped audit metadata."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass

from fastapi import Request

from apps.shared.core.client_ip import resolve_client_ip
from apps.shared.core.request_context import get_or_create_request_id

_audit_request_context_var: ContextVar[AuditRequestContext | None] = ContextVar(
    "audit_request_context",
    default=None,
)


@dataclass(frozen=True, slots=True)
class AuditRequestContext:
    """HTTP metadata captured for audit rows."""

    client_ip: str | None
    user_agent: str | None
    request_id: str | None

    @classmethod
    def from_request(cls, request: Request | None) -> AuditRequestContext:
        if request is None:
            return cls(client_ip=None, user_agent=None, request_id=None)
        ua = request.headers.get("user-agent")
        user_agent = ua[:512] if isinstance(ua, str) and ua.strip() else None
        return cls(
            client_ip=resolve_client_ip(request),
            user_agent=user_agent,
            request_id=get_or_create_request_id(request),
        )


EMPTY_AUDIT_REQUEST_CONTEXT = AuditRequestContext(client_ip=None, user_agent=None, request_id=None)


def set_current_audit_context(ctx: AuditRequestContext) -> Token:
    return _audit_request_context_var.set(ctx)


def reset_audit_context(token: Token) -> None:
    _audit_request_context_var.reset(token)


def get_current_audit_context() -> AuditRequestContext | None:
    return _audit_request_context_var.get()


def resolve_audit_request_context(explicit: AuditRequestContext | None) -> AuditRequestContext:
    if explicit is not None:
        return explicit
    return get_current_audit_context() or EMPTY_AUDIT_REQUEST_CONTEXT