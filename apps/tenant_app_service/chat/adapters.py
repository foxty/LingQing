"""Adapters for converting between domain models and DTOs."""

from apps.shared.artifact.domain import ArtifactDomain
from apps.shared.db.models import Artifact, ChatMessage, ChatThread, SessionSummary, ThreadSummary
from apps.tenant_app_service.chat.domain import MessageDomain, SessionSummaryDomain, ThreadDomain, ThreadSummaryDomain
from apps.tenant_app_service.chat.schemas import ConversationHistoryResponse, Message
from apps.tenant_app_service.hitl.utils import has_hitl_payload


def chat_message_to_domain(db_msg: ChatMessage) -> MessageDomain:
    """Convert ChatMessage DB model to MessageDomain.

    Args:
        db_msg: Database ChatMessage object

    Returns:
        MessageDomain instance
    """
    message_meta = db_msg.message_metadata or {}
    additional_kwargs = db_msg.additional_kwargs or {}
    timestamp = db_msg.timestamp  # Get timestamp from dedicated field
    msg_type = db_msg.type

    # Extract tool_calls from dedicated field for AI messages
    tool_calls = db_msg.tool_calls if msg_type == "ai" else None

    # Extract tool_call_id for tool messages
    tool_call_id = additional_kwargs.get("tool_call_id") if msg_type == "tool" else None

    # Extract message_id
    message_id = db_msg.message_id if db_msg.message_id else str(db_msg.id)

    return MessageDomain(
        message_id=message_id,
        thread_id=db_msg.thread_id,
        role=msg_type,
        content=db_msg.content,
        timestamp=timestamp,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        session_id=db_msg.session_id,
        agent_id=db_msg.agent_id,
        additional_kwargs=additional_kwargs,
        message_metadata=message_meta,
    )


def chat_thread_to_domain(db_thread: ChatThread) -> ThreadDomain:
    thread = ThreadDomain(
        id=db_thread.id,
        tenant_id=db_thread.tenant_id,
        user_id=db_thread.user_id,
        agent_id=db_thread.agent_id,
        title=db_thread.title,
        message_count=db_thread.message_count,
        created_at=db_thread.created_at,
        updated_at=db_thread.updated_at,
    )
    return thread


def db_artifact_to_domain(db_artifact: Artifact) -> ArtifactDomain:
    """Convert Artifact DB model to ArtifactDomain.

    Args:
        db_artifact: Database Artifact object

    Returns:
        ArtifactDomain instance
    """
    return ArtifactDomain(
        id=db_artifact.id,
        thread_id=db_artifact.source_thread_id,
        tenant_id=db_artifact.tenant_id,
        owner_id=db_artifact.owner_id,
        artifact_type=db_artifact.artifact_type,
        resource_id=db_artifact.resource_id,
        title=db_artifact.title,
        url=db_artifact.url,
        artifact_metadata=db_artifact.artifact_metadata,
        created_at=db_artifact.created_at,
        updated_at=db_artifact.updated_at,
        owner_username=db_artifact.owner_user.username if db_artifact.owner_user else None,
    )


def chat_messages_to_domain_list(db_messages: list[ChatMessage]) -> list[MessageDomain]:
    """Convert list of ChatMessage DB models to domain messages.

    Args:
        db_messages: List of ChatMessage objects from database

    Returns:
        List of MessageDomain instances
    """
    return [chat_message_to_domain(db_msg) for db_msg in db_messages]


def domain_message_to_api(domain_msg: MessageDomain) -> Message:
    """Convert Domain Message to API Message."""
    additional_kwargs = domain_msg.additional_kwargs
    role = domain_msg.role
    if role == "tool" and has_hitl_payload(domain_msg):
        role = "ai"

    return Message(
        message_id=domain_msg.message_id,
        thread_id=domain_msg.thread_id,
        agent_id=domain_msg.agent_id,
        role=role,
        content=domain_msg.content,
        timestamp=domain_msg.timestamp.isoformat() if domain_msg.timestamp else None,
        tool_calls=domain_msg.tool_calls,
        tool_call_id=domain_msg.tool_call_id,
        session_id=domain_msg.session_id,
        additional_kwargs=additional_kwargs,
        message_metadata=domain_msg.message_metadata,
    )


def domain_conversation_to_api(
    thread: ThreadDomain,
    username: str,
    next_before_created_at: str | None = None,
    next_before_id: int | None = None,
    next_before_session_id: str | None = None,
    has_more: bool | None = None,
) -> ConversationHistoryResponse:
    """Convert ThreadDomain to ConversationHistoryResponse DTO.

    Args:
        thread: Domain thread object with loaded messages
        username: Username for the conversation

    Returns:
        ConversationHistoryResponse DTO
    """
    messages = [domain_message_to_api(msg) for msg in thread.messages]

    return ConversationHistoryResponse(
        thread_id=thread.id,
        tenant_id=thread.tenant_id,
        agent_id=thread.agent_id,
        user_id=thread.user_id,
        username=username,
        total_rounds=thread.get_rounds(),
        messages=messages,
        message_count=thread.message_count,
        next_before_created_at=next_before_created_at,
        next_before_id=next_before_id,
        next_before_session_id=next_before_session_id,
        has_more=has_more,
    )


def domain_thread_to_api(thread: ThreadDomain) -> dict:
    """Convert ThreadDomain to API response dict.

    Used for thread metadata responses (without messages).
    """
    return {
        "id": thread.id,
        "tenant_id": thread.tenant_id,
        "user_id": thread.user_id,
        "agent_id": thread.agent_id,
        "title": thread.title,
        "message_count": thread.message_count,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
    }


def thread_summary_domain_to_db(domain: ThreadSummaryDomain) -> ThreadSummary:
    """Convert ThreadSummaryDomain to ThreadSummary DB model.

    Args:
        domain: ThreadSummaryDomain instance

    Returns:
        ThreadSummary DB model
    """
    return ThreadSummary(
        thread_id=domain.thread_id,
        tenant_id=domain.tenant_id,
        version=domain.version,
        summary_content=domain.summary_content,
        session_range=domain.session_range,
        message_range=domain.message_range,
        session_count=domain.session_count,
        token_count_before=domain.token_count_before,
        token_count_after=domain.token_count_after,
    )


def session_summary_to_domain(db_session: SessionSummary) -> SessionSummaryDomain:
    """Convert SessionSummary DB model to SessionSummaryDomain.

    Creates a SessionSummaryDomain with pre-extracted session data from DB cache.
    Used for thread summarization where full message history is not needed.

    Args:
        db_session: SessionSummary DB model

    Returns:
        SessionSummaryDomain instance with cached session summary data
    """
    # Create SessionSummaryDomain with pre-extracted data from DB cache
    session = SessionSummaryDomain.__new__(SessionSummaryDomain)
    session.session_id = db_session.session_id
    session.thread_id = db_session.thread_id
    session.user_intent = db_session.user_intent
    session.tools_used = db_session.tools_used
    session.key_results = db_session.key_results
    session.messages = []  # Not needed for cached summary
    session.message_time_range = db_session.message_range  # Use cached range from DB
    session.summary = db_session.summary_text
    return session


def artifact_domain_to_artifact_response(domain: ArtifactDomain) -> dict:
    """Convert ArtifactDomain to Artifact response dict for frontend.

    This matches the Artifact protocol used by agents when streaming artifacts.

    Args:
        domain: ArtifactDomain instance

    Returns:
        Dict matching Artifact protocol format
    """
    return {
        "type": "artifact",
        "artifact_type": domain.artifact_type,
        "id": domain.id,
        "url": domain.url,
        "title": domain.title or "Untitled",
        "metadata": domain.artifact_metadata,
    }
