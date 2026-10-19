"""SSE helpers and prepared-turn DTO for chat streaming."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.shared.core.exceptions import DomainException

# Keep bytes flowing during long LLM/tool gaps so proxies and browsers do not idle-close SSE.
SSE_HEARTBEAT_INTERVAL_SECONDS = 20
SSE_HEARTBEAT_PAYLOAD = ": ping\n\n"

STREAM_ERROR_KIND_DOMAIN = "domain"
STREAM_ERROR_KIND_RATE_LIMIT = "rate_limit"
STREAM_ERROR_KIND_AUTH = "auth"
STREAM_ERROR_KIND_TIMEOUT = "timeout"
STREAM_ERROR_KIND_CONNECTION = "connection"
STREAM_ERROR_KIND_INTERNAL = "internal"

STREAM_ERROR_GENERIC_MESSAGE = "Something went wrong while processing your request. Please try again."


def format_user_stream_error(error: BaseException) -> str:
    """Map an exception to a short, user-safe stream error message."""
    if isinstance(error, DomainException):
        return error.message

    error_message = str(error)
    lowered = error_message.lower()
    if "rate limit" in lowered:
        return "Rate limit exceeded. Please try again in a moment."
    if "api key" in lowered or "authentication" in lowered:
        return "Configuration error: Invalid API credentials."
    if "timeout" in lowered:
        return "Request timed out. Please try again."
    if "connection" in lowered:
        return "Connection error. Please check your network and try again."
    if error_message.strip():
        return f"An error occurred: {error_message}"
    return STREAM_ERROR_GENERIC_MESSAGE


def stream_error_kind(error: BaseException) -> str:
    """Stable category for clients that map errors to i18n (optional)."""
    if isinstance(error, DomainException):
        return STREAM_ERROR_KIND_DOMAIN

    lowered = str(error).lower()
    if "rate limit" in lowered:
        return STREAM_ERROR_KIND_RATE_LIMIT
    if "api key" in lowered or "authentication" in lowered:
        return STREAM_ERROR_KIND_AUTH
    if "timeout" in lowered:
        return STREAM_ERROR_KIND_TIMEOUT
    if "connection" in lowered:
        return STREAM_ERROR_KIND_CONNECTION
    return STREAM_ERROR_KIND_INTERNAL


def user_stream_error_sse_payload(error: BaseException) -> dict[str, str]:
    """Build SSE error event fields for a failed stream turn."""
    return {
        "type": "error",
        "message": format_user_stream_error(error),
        "error_code": type(error).__name__,
        "error_kind": stream_error_kind(error),
    }


@dataclass
class PreparedChatStream:
    """Setup result for a chat turn. Safe to use after the setup session closes."""

    session_id: str
    agent_id: int
    agent_name: str
    initial_messages: list[Any]
    thread_title: str | None
