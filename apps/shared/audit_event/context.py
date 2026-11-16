"""Request-scoped audit metadata."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from apps.shared.core.client_ip import resolve_client_ip
from apps.shared.core.request_context import get_or_create_request_id


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