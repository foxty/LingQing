"""SSE helpers and prepared-turn DTO for chat streaming."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Callable

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

_TRANSIENT_PG_MARKERS = (
    "connection is closed",
    "terminating connection",
    "administrator command",
    "connection reset",
    "server closed the connection",
    "could not connect",
    "connection refused",
)


def is_transient_postgres_connection_error(error: BaseException) -> bool:
    """True when Postgres was restarted or the TCP session dropped mid-use."""
    if not type(error).__module__.startswith("psycopg"):
        return False
    lowered = str(error).lower()
    return any(marker in lowered for marker in _TRANSIENT_PG_MARKERS)


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
    if is_transient_postgres_connection_error(error):
        return "Database connection lost. Retry the message; restart the backend if it keeps failing."
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
    if is_transient_postgres_connection_error(error) or "connection" in lowered:
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


def sse_stream_failure_lines(error: BaseException, session_id: str) -> list[str]:
    """SSE ``error`` + ``done`` lines when a stream body fails after prepare."""
    done_data = {"type": "done", "session_id": session_id}
    return [
        f"data: {json.dumps(user_stream_error_sse_payload(error))}\n\n",
        f"data: {json.dumps(done_data)}\n\n",
    ]


@dataclass
class PreparedChatStream:
    """Setup result for a chat turn. Safe to use after the setup session closes."""

    session_id: str
    agent_id: int
    agent_name: str
    initial_messages: list[Any]
    thread_title: str | None
    run_id: str | None = None
    trigger_message_id: str | None = None
    invoke_index: int = 0


def prepared_stream_opening_sse(prepared: PreparedChatStream) -> list[str]:
    """Initial SSE events after prepare (session id, optional thread title)."""
    lines = [
        f"data: {json.dumps({'type': 'session_started', 'session_id': prepared.session_id})}\n\n",
    ]
    if prepared.thread_title:
        lines.append(
            f"data: {json.dumps({'type': 'update_thread_title', 'title': prepared.thread_title})}\n\n",
        )
    return lines


async def iter_sse_from_event_queue(
    event_queue: asyncio.Queue[str | None],
    *,
    session_id: str,
    on_client_disconnect: Callable[[str], None] | None = None,
) -> AsyncIterator[str]:
    """Drain agent SSE chunks from a queue with heartbeats; survives client disconnect."""
    try:
        while True:
            try:
                item = await asyncio.wait_for(
                    event_queue.get(),
                    timeout=SSE_HEARTBEAT_INTERVAL_SECONDS,
                )
            except TimeoutError:
                yield SSE_HEARTBEAT_PAYLOAD
                continue
            if item is None:
                break
            yield item
    except asyncio.CancelledError:
        if on_client_disconnect is not None:
            on_client_disconnect(session_id)
        return
