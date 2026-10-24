"""Chat **Application** layer (orchestration): multi-session use-case entry points.

Composes Application Services (``ChatTurnService``, etc.) across committed DB sessions.
Routers and ingress import from here — not session-scoped services directly for streaming.
See ``AGENTS.md`` (Application vs Application Services) and ``turn_flow`` module docstring.
"""

from apps.tenant_app_service.chat.application.headless_flow import run_headless_chat_turn
from apps.tenant_app_service.chat.application.turn_flow import (
    complete_chat_turn_committed,
    iter_prepared_chat_stream_committed,
    prepare_chat_stream_committed,
    prepare_chat_turn_committed,
    run_non_stream_chat_turn,
    with_chat_service,
    with_chat_turn_service,
)

__all__ = [
    "complete_chat_turn_committed",
    "iter_prepared_chat_stream_committed",
    "prepare_chat_stream_committed",
    "prepare_chat_turn_committed",
    "run_headless_chat_turn",
    "run_non_stream_chat_turn",
    "with_chat_service",
    "with_chat_turn_service",
]
