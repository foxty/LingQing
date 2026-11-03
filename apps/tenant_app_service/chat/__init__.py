"""Chat module for agent interactions and thread management.

Layer map (see ``AGENTS.md`` — DDD four layers):

- **Presentation:** routers/ingress (outside this package); ``schemas`` = DTO contracts.
- **Application:** ``application/`` (orchestrating use cases); ``turn_service``, ``thread_service``,
  ``thread_run_service`` (session-scoped use cases); ``turn_admission`` (lock + busy gate in prepare txn).
- **Domain:** ``domain``, ``agent_run_domain`` — types, invariants, rules (no I/O).
- **Infrastructure:** ``*_repository``, ``agent_run_port_adapter``, ``run_context_adapter``,
  ``conversation_memory_manager``; ``streaming`` = SSE bytes (transport).

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
