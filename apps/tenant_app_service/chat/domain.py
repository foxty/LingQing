"""Domain models for chat module.

Unified domain model that treats Thread and Conversation as a single entity.
A Thread represents a chat session with both metadata (title, timestamps) and
conversation state (messages).
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, Literal

from langchain_core.messages import SystemMessage

from apps.shared.db.models import ChatMessage
from apps.shared.domain.base_domain_model import BaseDomainModel

if TYPE_CHECKING:
    pass

MESSAGE_TYPE_HUMAN: Final = "human"
MESSAGE_TYPE_AI: Final = "ai"
MESSAGE_TYPE_TOOL: Final = "tool"
MESSAGE_TYPE_SYSTEM: Final = "system"

SESSION_STATUS_RUNNING: Final = "running"
SESSION_STATUS_AWAITING_HITL: Final = "awaiting_hitl"
SESSION_STATUS_HITL_APPROVED_PENDING_CONTINUE: Final = "hitl_approved_pending_continue"
SESSION_STATUS_COMPLETED: Final = "completed"

# Orphaned runs (e.g. server reload after human persist) stop polling after this window.
SESSION_STALE_RUNNING_SECONDS: Final = 900


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

    def add_message_from_db(self, db_msg: ChatMessage) -> bool:
        """Add a message from database to conversation.

        Applies business rules for message filtering:
        - Only accepts human, ai, tool message types

        Args:
            db_msg: Database ChatMessage object

        Returns:
            True if message was added, False if filtered out
        """
        # Import here to avoid circular imports
        from apps.tenant_app_service.chat.adapters import chat_message_to_domain

        if db_msg.type not in ("human", "ai", "tool"):
            return False

        message_domain = chat_message_to_domain(db_msg)

        self.messages.append(message_domain)
        return True

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

    @classmethod
    def create_from_sessions(
        cls,
        thread_id: str,
        tenant_id: int,
        version: int,
        sessions: list["SessionSummaryDomain"],
        summary_content: str,
    ) -> "ThreadSummaryDomain":
        """Factory method to create ThreadSummaryDomain from sessions.

        Pure domain logic - no DB models, no services.

        Args:
            thread_id: Thread ID
            tenant_id: Tenant ID
            version: Version number
            sessions: List of SessionSummaryDomain objects
            summary_content: Pre-generated summary text (from LLM or fallback)

        Returns:
            ThreadSummaryDomain instance
        """
        from apps.tenant_app_service.agents.token_counter import count_tokens

        # Calculate session range
        session_range = {
            "from_session_id": sessions[0].session_id,
            "to_session_id": sessions[-1].session_id,
            "session_count": len(sessions),
        }

        # Calculate message time range
        all_times = []
        total_message_count = 0
        for session in sessions:
            time_range = session.message_time_range
            if time_range.get("from_time"):
                all_times.append(datetime.fromisoformat(time_range["from_time"]))
            if time_range.get("to_time"):
                all_times.append(datetime.fromisoformat(time_range["to_time"]))
            total_message_count += time_range.get("count", 0)

        message_range = {
            "from_time": min(all_times).isoformat() if all_times else None,
            "to_time": max(all_times).isoformat() if all_times else None,
            "count": total_message_count,
        }

        # Calculate token counts (align with trigger + LLM input: session summary text)
        session_messages = [
            SystemMessage(content=s.summary or f"{s.user_intent}\n{s.key_results}") for s in sessions
        ]
        token_count_before = count_tokens(session_messages)
        token_count_after = count_tokens([SystemMessage(content=summary_content)])

        return cls(
            thread_id=thread_id,
            tenant_id=tenant_id,
            version=version,
            summary_content=summary_content,
            session_range=session_range,
            message_range=message_range,
            session_count=len(sessions),
            token_count_before=token_count_before,
            token_count_after=token_count_after,
        )

    @classmethod
    def create_with_fallback_summary(
        cls,
        thread_id: str,
        tenant_id: int,
        version: int,
        sessions: list["SessionSummaryDomain"],
    ) -> "ThreadSummaryDomain":
        """Factory method to create ThreadSummaryDomain with domain-generated fallback summary.

        Use this when LLM summarization fails - domain knows how to summarize itself.

        Args:
            thread_id: Thread ID
            tenant_id: Tenant ID
            version: Version number
            sessions: List of SessionSummaryDomain objects

        Returns:
            ThreadSummaryDomain instance with fallback summary
        """
        summary_parts = [
            "# Thread Summary (no llm available)",
            "",
            f"Covered {len(sessions)} sessions.",
            "",
            "Recent sessions:",
        ]

        session_sums = [f"Session {s.session_id}:  {s.summary}" for s in sessions]
        summary_parts.append("\n".join(session_sums))

        fallback_content = "\n".join(summary_parts)

        # Use standard factory with generated summary
        return cls.create_from_sessions(
            thread_id=thread_id,
            tenant_id=tenant_id,
            version=version,
            sessions=sessions,
            summary_content=fallback_content,
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


@dataclass
class SessionSummaryDomain(BaseDomainModel):
    """Session summary domain model - represents a single conversation session.

    A session is one complete user interaction (user message + agent response).
    This model encapsulates business logic for extracting session information from messages.
    """

    session_id: str
    thread_id: str
    messages: list[MessageDomain]

    user_intent: str = field(init=False)
    tools_used: list[str] = field(init=False)
    key_results: str = field(init=False)
    message_time_range: dict = field(init=False)  # {from_time, to_time, count}
    summary: str = ""  # Placeholder for generated summary text

    def __post_init__(self) -> None:
        self.user_intent = self._extract_user_intent()
        self.tools_used = self._extract_tools_used()
        self.key_results = self._extract_key_results()
        self.message_time_range = self._compute_message_time_range()

    def _extract_user_intent(self) -> str:
        """Extract user intent from first human message.

        Returns:
            User intent string (truncated to 500 chars)
        """
        for msg in self.messages:
            if msg.role == "human":
                content = msg.content.strip()
                return content[:500] if len(content) > 500 else content
        return "No user intent found"

    def _extract_tools_used(self) -> list[str]:
        """Extract unique tools used in this session.

        Returns:
            Sorted list of unique tool names
        """
        tools = set()
        for msg in self.messages:
            if msg.role == "ai" and msg.tool_calls:
                for tc in msg.tool_calls:
                    if isinstance(tc, dict) and "name" in tc:
                        tools.add(tc["name"])
        return sorted(list(tools))

    def _extract_key_results(self) -> str:
        """Extract key results from last AI message without tool calls.

        Returns:
            Key results string
        """
        for msg in reversed(self.messages):
            if msg.role == "ai" and not msg.tool_calls:
                return msg.content.strip()
        return "No results found"

    def _compute_message_time_range(self) -> dict:
        """Compute time range of messages in this session.

        Returns:
            Dict with from_time, to_time (ISO format), and count
        """
        if not self.messages:
            return {"from_time": None, "to_time": None, "count": 0}

        timestamps = [m.timestamp for m in self.messages if m.timestamp]
        if not timestamps:
            return {"from_time": None, "to_time": None, "count": len(self.messages)}

        return {
            "from_time": min(timestamps).isoformat(),
            "to_time": max(timestamps).isoformat(),
            "count": len(self.messages),
        }

    def ready_for_llm_summary(self) -> bool:
        """Determine if session is ready for summary generation by llm.

        Criteria:
        - At least one human message
        - At least one AI message

        Returns:
            True if ready for summary, False otherwise
        """
        has_enough_messages = len(self.messages) >= 3
        has_tool_calls = len(self.tools_used) > 0
        has_big_results = len(self.key_results) >= 1000
        if has_big_results:
            return True
        else:
            return has_enough_messages and has_tool_calls

    def gen_summary_text(self) -> str:
        """Generate a brief text summary of the session.

        Returns:
            Summary text
        """
        summary = f"\n**Session ({self.session_id}) Summary**:\n"
        summary += f"User Intent: {self.user_intent}\n"
        summary += f"Tools Used: {', '.join(self.tools_used) if self.tools_used else 'None'}\n"
        summary += f"Key Results: {self.key_results}\n"
        return summary

    @classmethod
    def from_messages(cls, session_id: str, thread_id: str, messages: list[MessageDomain]) -> "SessionSummaryDomain":
        """Create SessionSummaryDomain from domain messages.

        Domain model depends only on MessageDomain, not DB models.
        Conversion from DB should happen at the caller level via adapters.

        Args:
            session_id: Session ID
            thread_id: Thread ID
            messages: List of MessageDomain objects (pre-converted from DB)

        Returns:
            SessionSummaryDomain instance
        """
        return cls(
            session_id=session_id,
            thread_id=thread_id,
            messages=messages,
        )


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
