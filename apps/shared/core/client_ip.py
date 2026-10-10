"""Resolve client IP for rate limiting and audit (behind nginx / reverse proxies)."""

from __future__ import annotations

import ipaddress

from fastapi import Request

from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def _parse_ip(value: str) -> str | None:
    first = (value or "").strip().split(",", maxsplit=1)[0].strip()
    if not first:
        return None
    try:
        return str(ipaddress.ip_address(first))
    except ValueError:
        return None


def resolve_client_ip(request: Request) -> str | None:
    """Return client IP from trusted proxy headers, else the direct peer address."""
    for header in ("x-real-ip", "x-forwarded-for"):
        raw = request.headers.get(header)
        if not raw:
            continue
        parsed = _parse_ip(raw)
        if parsed:
            return parsed

    if request.client and request.client.host:
        peer = request.client.host.strip()
        parsed = _parse_ip(peer)
        if parsed:
            return parsed

    return None


def client_ip_key(request: Request) -> str:
    """Rate-limit bucket key from client IP; logs when resolution fails."""
    ip = resolve_client_ip(request)
    if ip:
        return ip

    logger.warning(
        "Could not resolve client IP; using shared rate-limit bucket 'unknown' "
        "method=%s path=%s has_x_real_ip=%s has_x_forwarded_for=%s has_client=%s",
        request.method,
        request.url.path,
        bool(request.headers.get("x-real-ip")),
        bool(request.headers.get("x-forwarded-for")),
        request.client is not None,
    )
    return "unknown"
