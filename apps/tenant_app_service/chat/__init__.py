"""Chat module for agent interactions and thread management.

Layer map (inward dependencies only):

- ``application/`` — **Application** orchestration (multi-session entry: HTTP stream, headless).
- ``turn_service``, ``thread_service``, ``thread_run_service`` —
  **Application Services** (one ``AsyncSession`` per call).
- ``turn_admission`` — Postgres advisory lock + busy gate (prepare transaction).
- ``domain``, ``agent_run_domain`` — Pure domain types and rules (no I/O).
- ``*_repository`` — Persistence adapters.
- ``streaming`` — SSE transport only.
- ``schemas`` — HTTP/DTO contracts.

Routers and ingress import ``application`` for turns; not ``ChatTurnService`` directly for streaming.
"""

from apps.tenant_app_service.chat.domain import MessageDomain, ThreadDomain
from apps.tenant_app_service.chat.repository import ThreadRepository
from apps.tenant_app_service.chat.schemas import (
    ChatRequest,
    ChatResponse,
    Message,
    ThreadCreate,
    ThreadResponse,
    ThreadUpdate,
)
from apps.tenant_app_service.chat.thread_service import ThreadService
from apps.tenant_app_service.chat.turn_service import ChatTurnService

__all__ = [
    "ChatTurnService",
    "ThreadService",
    "MessageDomain",
    "ThreadDomain",
    "ThreadRepository",
    "Message",
    "ChatRequest",
    "ChatResponse",
    "ThreadCreate",
    "ThreadResponse",
    "ThreadUpdate",
]
