"""HTTP request context helpers for logging and error correlation."""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi import Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from apps.config import get_settings
from apps.shared.core.auth import AUTH_COOKIE_NAME
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


def get_or_create_request_id(request: Request) -> str:
    """Return the inbound request id or generate one for this request."""
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str) and existing.strip():
        return existing

    header_value = request.headers.get(REQUEST_ID_HEADER)
    request_id = header_value.strip() if isinstance(header_value, str) and header_value.strip() else uuid4().hex
    request.state.request_id = request_id
    return request_id


def _peek_auth_context(request: Request) -> tuple[str | None, str | None]:
    """Best-effort tenant/user extraction for logging (no DB lookup)."""
    token: str | None = None
    auth_header = request.headers.get("authorization")
    if isinstance(auth_header, str) and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    else:
        cookie = request.cookies.get(AUTH_COOKIE_NAME)
        if isinstance(cookie, str) and cookie.strip():
            token = cookie.strip()
            if token.lower().startswith("bearer "):
                token = token[7:].strip()

    if not token:
        return None, None

    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None, None

    tenant_id = payload.get("tenant_id")
    user_id = payload.get("user_id")
    tenant = str(tenant_id) if isinstance(tenant_id, int) else None
    user = str(user_id) if isinstance(user_id, int) else None
    return tenant, user


def format_request_context(request: Request) -> str:
    """Compact request context string for exception and audit logs."""
    request_id = get_or_create_request_id(request)
    tenant_id, user_id = _peek_auth_context(request)
    tenant = tenant_id or request.headers.get("x-tenant-id") or "unknown"
    user = user_id or "unknown"
    return (
        f"request_id={request_id} method={request.method} path={request.url.path} "
        f"tenant={tenant} user={user}"
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attach request_id and emit one structured access log line per request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path.endswith("/health"):
            return await call_next(request)

        request_id = get_or_create_request_id(request)
        tenant_id, user_id = _peek_auth_context(request)
        started = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            log_line = (
                "HTTP request request_id=%s method=%s path=%s status=%s duration_ms=%s "
                "tenant_id=%s user_id=%s"
            )
            log_args = (
                request_id,
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                tenant_id or "-",
                user_id or "-",
            )
            if status_code >= 500:
                logger.error(log_line, *log_args)
            elif status_code >= 400:
                logger.warning(log_line, *log_args)
            else:
                logger.info(log_line, *log_args)
