"""Domain models for chat module.

Unified domain model that treats Thread and Conversation as a single entity.
A Thread represents a chat session with both metadata (title, timestamps) and
conversation state (messages).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Literal

from apps.shared.domain.base_domain_model import BaseDomainModel

if TYPE_CHECKING:
    pass

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
    tool_calls: list[dict[str, Any]] | None = None  # For AI messages with tool calls
    tool_call_id: str | None = None  # For tool messages (references the tool call)
    additional_kwargs: dict[str, Any] | None = None  # Full additional metadata
    message_metadata: dict[str, Any] | None = None  # Full message metadata


@dataclass
class ThreadDomain(BaseDomainModel):
    """Unified Thread domain model.

    Represents a chat session with both:
    - Metadata: title, timestamps, message count (persisted in DB)
    - Conversation state: messages (persisted in checkpointer, loaded on demand)

    This unifies the previous ThreadDomain and ConversationDomain concepts.
    """

    # Core identity
    id: str
    tenant_id: int
    user_id: int
    agent_id: int

    # Metadata (always loaded from DB)
    title: str | None = None
    message_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # Conversation state (loaded on demand from checkpointer)
    messages: list[MessageDomain] = field(default_factory=list)

    def get_rounds(self) -> int:
        """Get conversation rounds (pairs of human-ai messages)."""
        human_count = sum(1 for m in self.messages if m.role == "human")
        return human_count


@dataclass
class ThreadSummaryDomain(BaseDomainModel):
    """Domain model for thread summary - versioned compression of thread history.

    Represents a summary of multiple sessions with token compression metrics.
    Pure domain model with no infrastructure dependencies.
    """

    thread_id: str
    tenant_id: int
    version: int
    summary_content: str
    session_range: dict  # {from_session_id, to_session_id, session_count}
    message_range: dict  # {from_time, to_time, count}
    session_count: int
    token_count_before: int
    token_count_after: int
    created_at: datetime | None = None
    through_trigger_message_id: str | None = None

    @classmethod
    def create_cumulative(
        cls,
        *,
        thread_id: str,
        tenant_id: int,
        version: int,
        through_trigger_message_id: str,
        summary_content: str,
        session_range: dict,
        message_range: dict,
        session_count: int,
        token_count_before: int,
        token_count_after: int,
    ) -> "ThreadSummaryDomain":
        """Cumulative thread status merged from the previous version plus aged-out turns."""
        return cls(
            thread_id=thread_id,
            tenant_id=tenant_id,
            version=version,
            summary_content=summary_content,
            session_range=session_range,
            message_range=message_range,
            session_count=session_count,
            token_count_before=token_count_before,
            token_count_after=token_count_after,
            through_trigger_message_id=through_trigger_message_id,
        )

    def get_token_savings(self) -> int:
        """Calculate token savings from compression."""
        return self.token_count_before - self.token_count_after

    def get_compression_ratio(self) -> float:
        """Return output/input token ratio (values above 1.0 mean expansion)."""
        if self.token_count_before == 0:
            return 0.0
        return self.token_count_after / self.token_count_before

    def format_token_metrics(self) -> str:
        """Format token delta for logging."""
        savings = self.get_token_savings()
        ratio_pct = self.get_compression_ratio() * 100
        if savings >= 0:
            return f"saved {savings} tokens ({ratio_pct:.1f}% of input)"
        return f"expanded by {-savings} tokens ({ratio_pct:.1f}% of input)"


def extract_tool_call_ids(tool_calls: list[dict[str, Any]] | None) -> list[str]:
    """Extract tool call IDs from an AI message tool_calls payload."""
    if not tool_calls:
        return []
    return [tool_call_id for tc in tool_calls if isinstance(tc, dict) and (tool_call_id := tc.get("id"))]


def is_tool_chain_resolved(
    tool_call_ids: list[str],
    resolved_tool_call_ids: set[str],
    has_final_ai_after_tools: bool,
) -> bool:
    """Return True when a tool-call chain is complete and no longer needs HITL injection.

    A chain is resolved when every tool call has a tool response and a final AI
    message exists after the last tool response.
    """
    if not tool_call_ids:
        return False
    if not resolved_tool_call_ids.issuperset(tool_call_ids):
        return False
    return has_final_ai_after_tools
