"""Chat module for agent interactions and thread management.

Layer map (see ``AGENTS.md`` — DDD four layers):

- **Presentation:** ``schemas`` (DTOs); routers live under ``tenant_app_service/routers``.
- **Application:** ``application/`` — ``turn/``, ``runs/``, ``threads/``, ``turn_flow``, ``queries/``.
- **Domain:** ``domain/`` — aggregates, policies, ``ports/``.
- **Infrastructure:** ``infrastructure/persistence/``, ``infrastructure/adapters/``.

Legacy import paths (``thread_run_service``, ``turn_service``, adapters at package root) re-export from the layers above.
Composition helpers: ``chat.deps``.
"""

from apps.tenant_app_service.chat.application.runs import ThreadRunService
from apps.tenant_app_service.chat.application.threads import ThreadService
from apps.tenant_app_service.chat.application.turn import ChatTurnService
from apps.tenant_app_service.chat.domain import MessageDomain, ThreadDomain
from apps.tenant_app_service.chat.infrastructure.persistence.thread_repository import ThreadRepository
from apps.tenant_app_service.chat.schemas import (
    ChatRequest,
    ChatResponse,
    Message,
    ThreadCreate,
    ThreadResponse,
    ThreadUpdate,
)

__all__ = [
    "ChatTurnService",
    "ThreadRunService",
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
