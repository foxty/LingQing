"""Unified thread management router.

Handles both thread metadata (title, timestamps) and conversation history (messages).
Previously split between threads.py and history.py, now consolidated for better API design.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.schemas import ArtifactResponse
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.exceptions import (
    AuthorizationError,
    InternalServiceError,
    ResourceNotFoundError,
)
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat import ChatService
from apps.tenant_app_service.chat.schemas import (
    ConversationHistoryResponse,
    Message,
    SessionStatusResponse,
    ThreadCreate,
    ThreadResponse,
    ThreadUpdate,
)

router = APIRouter(prefix="/threads", tags=["threads"], include_in_schema=False)

logger = get_logger(__name__)


def _assert_user_owns_thread(thread, current_user: UserDTO) -> None:
    if thread.tenant_id != current_user.tenant_id or thread.user_id != current_user.id:
        raise AuthorizationError("Access denied")


# ============================================================================
# Thread Metadata Operations
# ============================================================================


@router.post("", response_model=ThreadResponse)
async def create_thread(
    request: ThreadCreate,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Create a new thread.

    Args:
        request: Thread creation request
        current_user: Current authenticated user
        db: Database session

    Returns:
        Created thread metadata
    """
    chat_service = ChatService(current_user.tenant_id, db)

    thread = await chat_service.create_thread(
        user_id=current_user.id,
        agent_id=request.agent_id,
        title=request.title,
        first_message=request.first_message,
    )

    return ThreadResponse(
        id=thread.id,
        tenant_id=thread.tenant_id,
        user_id=thread.user_id,
        agent_id=thread.agent_id,
        title=thread.title,
        message_count=thread.message_count,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.get("", response_model=list[ThreadResponse])
async def list_threads(
    agent_id: int | None = Query(None, description="Filter threads by agent ID"),
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """List all threads for the current user.

    Args:
        agent_id: Optional agent ID to filter threads by specific agent
        current_user: Current authenticated user
        db: Database session

    Returns:
        List of threads ordered by updated_at desc
    """
    chat_service = ChatService(current_user.tenant_id, db)
    actor = ActorContext(tenant_id=current_user.tenant_id, user_id=current_user.id, user_role=current_user.role)

    threads = await chat_service.list_user_threads(current_user.id, agent_id=agent_id, actor=actor)

    return [
        ThreadResponse(
            id=t.id,
            tenant_id=t.tenant_id,
            user_id=t.user_id,
            agent_id=t.agent_id,
            title=t.title,
            message_count=t.message_count,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in threads
    ]


@router.get("/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Get thread metadata.

    Args:
        thread_id: Thread ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Thread metadata (without messages)

    Raises:
        HTTPException: If thread not found or unauthorized
    """
    chat_service = ChatService(current_user.tenant_id, db)

    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")

    _assert_user_owns_thread(thread, current_user)

    return ThreadResponse(
        id=thread.id,
        tenant_id=thread.tenant_id,
        user_id=thread.user_id,
        agent_id=thread.agent_id,
        title=thread.title,
        message_count=thread.message_count,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


@router.patch("/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: str,
    request: ThreadUpdate,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Update thread metadata (e.g., title).

    Args:
        thread_id: Thread ID
        request: Thread update request
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated thread metadata

    Raises:
        HTTPException: If thread not found or unauthorized
    """
    chat_service = ChatService(current_user.tenant_id, db)

    # Verify thread exists and user owns it
    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    _assert_user_owns_thread(thread, current_user)

    # Update title
    updated_thread = await chat_service.update_thread_title(thread_id, request.title)
    if not updated_thread:
        raise InternalServiceError("Failed to update thread")

    return ThreadResponse(
        id=updated_thread.id,
        tenant_id=updated_thread.tenant_id,
        user_id=updated_thread.user_id,
        agent_id=updated_thread.agent_id,
        title=updated_thread.title,
        message_count=updated_thread.message_count,
        created_at=updated_thread.created_at,
        updated_at=updated_thread.updated_at,
    )


@router.delete("/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Delete a thread and all its messages.

    This removes:
    - Thread metadata from database
    - All conversation messages from checkpointer
    - Associated temporary tables

    Args:
        thread_id: Thread ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        HTTPException: If thread not found or unauthorized
    """
    chat_service = ChatService(current_user.tenant_id, db)

    # Verify thread exists and user owns it
    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    _assert_user_owns_thread(thread, current_user)

    # Delete thread and all associated data
    success = await chat_service.delete_thread(thread_id)
    if not success:
        raise InternalServiceError("Failed to delete thread")

    return {"message": "Thread and all messages deleted successfully"}


# ============================================================================
# Conversation History Operations (nested under thread)
# ============================================================================


@router.get("/{thread_id}/messages", response_model=ConversationHistoryResponse)
async def get_thread_messages(
    thread_id: str,
    session_limit: int = Query(
        5,
        ge=1,
        le=50,
        description="Maximum number of sessions to return (returns full messages per session)",
    ),
    before_session_id: str | None = Query(None, description="Cursor session ID for loading older sessions"),
    include_tool_messages: bool | None = Query(
        None,
        description="Whether to include tool messages in history. If omitted, uses server default.",
    ),
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Get conversation history (messages) for a thread.

    Args:
        thread_id: Thread ID
        session_limit: Maximum number of sessions to return
        current_user: Current authenticated user
        db: Database session

    Returns:
        Conversation history with messages

    Raises:
        HTTPException: If thread not found or unauthorized
    """
    chat_service = ChatService(current_user.tenant_id, db)

    # Verify thread exists and user owns it
    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    _assert_user_owns_thread(thread, current_user)

    # Get conversation history (loads messages from checkpointer)
    # Note: We pass agent_id from thread metadata
    return await chat_service.get_conversation_history(
        agent_id=thread.agent_id,
        current_user=current_user,
        thread_id=thread_id,
        session_limit=session_limit,
        before_session_id=before_session_id,
        include_tool_messages=include_tool_messages,
    )


@router.get("/{thread_id}/sub-agent/{sub_agent_id}/messages", response_model=ConversationHistoryResponse)
async def get_sub_agent_messages(
    thread_id: str,
    sub_agent_id: str,
    session_id: str = Query(..., description="Session ID for filtering messages"),
    session_limit: int = Query(
        5,
        ge=1,
        le=50,
        description="Maximum number of sessions to return (returns full messages per session)",
    ),
    before_session_id: str | None = Query(None, description="Cursor session ID for loading older sessions"),
    include_tool_messages: bool | None = Query(
        None,
        description="Whether to include tool messages in history. If omitted, uses server default.",
    ),
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Get internal messages from a sub-agent (capability execution details).

    Args:
        thread_id: Parent thread ID
        sub_agent_id: Sub-agent ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        GroupMessagesResponse DTO (group_id will be the sub_agent_id)

    Raises:
        HTTPException: If thread not found or unauthorized
    """
    chat_service = ChatService(current_user.tenant_id, db)

    # Verify parent thread exists and user owns it
    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    _assert_user_owns_thread(thread, current_user)
    logger.info(f"Fetching messages for sub-agent {sub_agent_id} in thread {thread_id} with session {session_id}")
    return await chat_service.get_conversation_history(
        agent_id=sub_agent_id,
        current_user=current_user,
        thread_id=thread_id,
        session_id=session_id,
        session_limit=session_limit,
        before_session_id=before_session_id,
        include_tool_messages=include_tool_messages,
    )


@router.get("/{thread_id}/tool-calls/{tool_call_id}", response_model=Message)
async def get_tool_call_detail(
    thread_id: str,
    tool_call_id: str,
    session_id: str | None = Query(None, description="Optional session_id to scope tool call lookup"),
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Get a single tool call detail message for lazy-loading tool card details."""
    chat_service = ChatService(current_user.tenant_id, db)

    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    _assert_user_owns_thread(thread, current_user)

    message = await chat_service.get_tool_call_detail(
        thread_id=thread_id,
        tool_call_id=tool_call_id,
        session_id=session_id,
    )
    if not message:
        raise ResourceNotFoundError(f"Tool call detail not found: {tool_call_id}")

    return message


@router.get("/{thread_id}/session-status", response_model=SessionStatusResponse)
async def get_thread_session_status(
    thread_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Get durable session status for polling in-progress agent turns."""
    chat_service = ChatService(current_user.tenant_id, db)

    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    _assert_user_owns_thread(thread, current_user)

    return await chat_service.get_session_status(thread_id=thread_id, agent_id=thread.agent_id)


# ============================================================================
# Thread Artifact Link Operations
# ============================================================================


@router.get("/{thread_id}/artifacts", response_model=list[ArtifactResponse])
async def list_linked_artifacts(
    thread_id: str,
    artifact_type: str | None = Query(None, description="Filter by artifact type"),
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Get all artifacts linked to a thread.

    Users can call this API when entering a thread to load historical artifacts.

    Args:
        thread_id: Thread ID
        artifact_type: Optional type filter (dashboard, chart, report, etc.)
        current_user: Current authenticated user
        db: Database session

    Returns:
        List of artifacts linked to the thread

    Raises:
        ResourceNotFoundError: If thread not found
        AuthorizationError: If user doesn't have access to the thread
    """
    from apps.shared.artifact.repository import ArtifactRepository
    from apps.tenant_app_service.chat.repository import ThreadRepository

    # Verify thread exists and user has access
    thread_repo = ThreadRepository(db)
    thread = await thread_repo.get_by_id(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    _assert_user_owns_thread(thread, current_user)

    # Get artifacts
    artifact_repo = ArtifactRepository(db)
    artifacts = await artifact_repo.list_linked_artifacts(thread_id, artifact_type)

    logger.info(
        f"Fetched {len(artifacts)} artifacts for thread {thread_id}",
        extra={"thread_id": thread_id, "artifact_type": artifact_type, "count": len(artifacts)},
    )

    # Convert domain to response DTO
    return [
        ArtifactResponse(
            type="artifact",
            artifact_type=a.artifact_type,
            id=a.id,
            resource_id=a.resource_id,
            url=a.url,
            title=a.title or "Untitled",
            metadata=a.artifact_metadata,
            created_at=a.created_at,
            owner_username=a.owner_user.username if a.owner_user else None,
        )
        for a in artifacts
    ]


@router.delete("/{thread_id}/artifacts/{artifact_id}")
async def unlink_artifact_link(
    thread_id: str,
    artifact_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Unlink an artifact from a thread.

    Note: This only removes the association, not the actual artifact resource (e.g., Dashboard).

    Args:
        thread_id: Thread ID
        artifact_id: Artifact ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message

    Raises:
        ResourceNotFoundError: If thread or artifact not found
        AuthorizationError: If user doesn't have access
    """
    from apps.shared.artifact.repository import ArtifactRepository
    from apps.tenant_app_service.chat.repository import ThreadRepository

    # Verify thread exists and user has access
    thread_repo = ThreadRepository(db)
    thread = await thread_repo.get_by_id(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    _assert_user_owns_thread(thread, current_user)

    artifact_repo = ArtifactRepository(db)
    success = await artifact_repo.unlink_by_id(artifact_id, thread_id)

    if not success:
        raise ResourceNotFoundError(f"Artifact {artifact_id} not found in thread")

    await db.commit()

    logger.info(
        f"Unlinked artifact {artifact_id} from thread {thread_id}",
        extra={"thread_id": thread_id, "artifact_id": artifact_id},
    )

    return {"message": "Artifact unlinked successfully"}
