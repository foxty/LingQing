"""Thread and in-checkpointer message entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Literal

from apps.shared.domain.base_domain_model import BaseDomainModel

MESSAGE_TYPE_HUMAN: Final = "human"
MESSAGE_TYPE_AI: Final = "ai"
MESSAGE_TYPE_TOOL: Final = "tool"
MESSAGE_TYPE_SYSTEM: Final = "system"


@dataclass
class MessageDomain(BaseDomainModel):
    """Message domain model for chat conversations."""

    role: Literal["human", "ai", "tool", "system"]
    content: str
    message_id: str
    thread_id: str
    session_id: str
    agent_id: int
    timestamp: datetime | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    additional_kwargs: dict[str, Any] | None = None
    message_metadata: dict[str, Any] | None = None


@dataclass
class ThreadDomain(BaseDomainModel):
    """Thread metadata plus optional checkpointer-backed messages."""

    id: str
    tenant_id: int
    user_id: int
    agent_id: int
    title: str | None = None
    message_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    messages: list[MessageDomain] = field(default_factory=list)

    def get_rounds(self) -> int:
        human_count = sum(1 for m in self.messages if m.role == "human")
        return human_count
