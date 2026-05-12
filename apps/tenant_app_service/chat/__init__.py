"""Chat module for agent interactions and thread management.

Unified module that handles both conversation state (messages) and
thread metadata (title, timestamps). Previously split between chat
and thread modules, now consolidated for better cohesion.

External modules should only import the service layer and public DTOs.
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
from apps.tenant_app_service.chat.service import ChatService

__all__ = [
    "ChatService",
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
