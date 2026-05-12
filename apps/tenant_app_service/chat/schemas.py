"""DTOs for chat module."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SimpleMessage(BaseModel):
    """Simple message model for chat requests (aligned with frontend).

    Only contains the essential fields that frontend needs to send.
    """

    role: Literal["human"]
    content: str


class Message(BaseModel):
    """Message model with strict role validation.

    Roles use LangChain's standard naming: 'human', 'ai', 'tool', 'system'
    This avoids unnecessary type conversion between API and LangChain layers.
    """

    message_id: str | None = None
    role: Literal["human", "ai", "tool", "system"]
    content: str
    agent_id: int
    thread_id: str
    timestamp: str | None = None  # ISO 8601 format timestamp
    tool_calls: list[dict[str, Any]] | None = None  # For AI messages with tool calls
    tool_call_id: str | None = None  # For tool messages (results)
    session_id: str | None = None  # For linking to observability metrics
    additional_kwargs: dict[str, Any] | None = None  # Additional metadata (e.g., tool_metadata)
    message_metadata: dict[str, Any] | None = None  # Full message metadata


class ContextResourceRef(BaseModel):
    """Reference to a context resource selected via @mention."""

    resource_type: str = Field(
        ..., description="Resource type: document, dashboard, report, scheduled_task, app, asset"
    )
    resource_id: int = Field(..., description="Primary key of the resource")


class ChatRequest(BaseModel):
    """Chat request model."""

    tenant_id: int = Field(description="Tenant ID")
    agent_id: int = Field(description="Agent ID")
    message: SimpleMessage  # Use simple message type for requests
    thread_id: str | None = Field(None, description="Thread ID for conversation continuity")
    stream: bool = False
    selected_artifact_id: int | None = Field(
        None,
        description="Deprecated: use selected_resource_ids instead. Single artifact ID for backward compat.",
    )
    selected_resource_ids: list[ContextResourceRef] | None = Field(
        None,
        description="Context resources selected via @mention to include as context for this message",
    )
    hitl_proposal_id: str | None = Field(None, description="Resolved HITL proposal id for continuation")
    hitl_action: Literal["approved"] | None = Field(
        None,
        description="HITL approve continuation only; reject is handled via HITL API",
    )


class ChatResponse(BaseModel):
    """Chat response model."""

    response: Message
    agent_id: int
    tenant_id: int


# ============ History DTOs ============


class ConversationHistoryResponse(BaseModel):
    """Conversation history response."""

    thread_id: str
    tenant_id: int
    agent_id: int
    user_id: int
    username: str
    total_rounds: int  # Number of complete user-assistant exchanges
    messages: list[Message]
    message_count: int  # Total messages in conversation
    next_before_created_at: str | None = None  # Cursor timestamp for older messages
    next_before_id: int | None = None  # Cursor DB id for older messages
    next_before_session_id: str | None = None  # Cursor session id for older sessions
    has_more: bool | None = None  # Whether more older messages exist


class ClearConversationResponse(BaseModel):
    """Clear conversation response."""

    message: str
    thread_id: str


# ============ Thread DTOs ============


class ThreadCreate(BaseModel):
    """Thread creation request."""

    agent_id: int = Field(..., description="Agent ID for this thread")
    title: str | None = Field(None, description="Optional thread title")
    first_message: str | None = Field(None, description="Optional first message to auto-generate title")


class ThreadUpdate(BaseModel):
    """Thread update request."""

    title: str = Field(..., description="New thread title")


class ThreadResponse(BaseModel):
    """Thread response."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Thread ID")
    tenant_id: int = Field(..., description="Tenant ID")
    user_id: int = Field(..., description="User ID")
    agent_id: int = Field(..., description="Agent ID")
    title: str | None = Field(None, description="Thread title")
    message_count: int = Field(..., description="Number of messages in thread")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


SessionStatus = Literal[
    "running",
    "awaiting_hitl",
    "hitl_approved_pending_continue",
    "completed",
]


class PendingHitlInfo(BaseModel):
    """Pending HITL approval metadata for session-status."""

    proposal_id: str
    tool_name: str
    session_id: str | None = None


class ApprovedHitlInfo(BaseModel):
    """Approved HITL awaiting agent continuation."""

    proposal_id: str
    tool_name: str
    session_id: str | None = None


class SessionStatusResponse(BaseModel):
    """Active session status for durable chat polling."""

    session_id: str | None = None
    status: SessionStatus
    has_ai_response: bool = False
    pending_hitl: PendingHitlInfo | None = None
    approved_hitl: ApprovedHitlInfo | None = None


# ArtifactResponse is now owned by apps.shared.artifact.schemas.
