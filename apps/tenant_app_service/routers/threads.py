"""Unified thread management router.

Handles both thread metadata (title, timestamps) and conversation history (messages).
Previously split between threads.py and history.py, now consolidated for better API design.
"""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import EnvConfig
from apps.shared.artifact.schemas import ArtifactResponse
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.exceptions import (
    AuthorizationError,
    InternalServiceError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.chat.compose_message import compose_thread_message
from apps.tenant_app_service.chat.membership_repository import ThreadMembershipRepository
from apps.tenant_app_service.chat.schemas import (
    ComposeThreadMessageRequest,
    ComposeThreadMessageResponse,
    ConversationHistoryResponse,
    Message,
    RoomMessageCreate,
    RoomMessageResponse,
    SessionStatusResponse,
    ThreadAgentAdd,
    ThreadAgentPrimaryUpdate,
    ThreadAgentRosterResponse,
    ThreadCreate,
    ThreadMemberAdd,
    ThreadMemberResponse,
    ThreadMemberRoleUpdate,
    ThreadResponse,
    ThreadUpdate,
)
from apps.tenant_app_service.chat.thread_access import require_read_thread, require_write_thread
from apps.tenant_app_service.chat.thread_kinds import MEMBER_ROLE_OWNER, THREAD_KIND_SHARED
from apps.tenant_app_service.chat.thread_service import ThreadService
from apps.tenant_app_service.tenant.user_directory import usernames_for_user_ids

router = APIRouter(prefix="/threads", tags=["threads"], include_in_schema=False)

logger = get_logger(__name__)


def _require_shared_threads_enabled() -> None:
    if not EnvConfig.SHARED_THREADS_ENABLED:
        raise ValidationError("Shared threads are not enabled for this environment")


async def _assert_user_owns_thread(thread, current_user: UserDTO, db: AsyncSession) -> None:
    await require_read_thread(db, thread_id=thread.id, user=current_user)


def _thread_response(thread) -> ThreadResponse:
    return ThreadResponse(
        id=thread.id,
        tenant_id=thread.tenant_id,
        user_id=thread.user_id,
        agent_id=thread.agent_id,
        thread_kind=getattr(thread, "thread_kind", None) or "personal",
        title=thread.title,
        message_count=thread.message_count,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


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
    chat_service = ThreadService(current_user.tenant_id, db)
    agent_ids = request.agent_ids or ([request.agent_id] if request.agent_id is not None else [])
    member_ids = request.member_user_ids
    needs_shared = len(agent_ids) > 1 or (member_ids and len(set(member_ids)) > 0)
    if needs_shared:
        _require_shared_threads_enabled()
        thread = await chat_service.create_conversation(
            owner_user_id=current_user.id,
            agent_ids=agent_ids,
            title=request.title,
            first_message=request.first_message,
            member_user_ids=member_ids,
        )
    else:
        thread = await chat_service.create_thread(
            user_id=current_user.id,
            agent_id=agent_ids[0],
            title=request.title,
            first_message=request.first_message,
        )

    return _thread_response(thread)


@router.get("", response_model=list[ThreadResponse])
async def list_threads(
    agent_id: int | None = Query(None, description="Filter threads by agent ID"),
    scope: str = Query("personal", description="personal | shared | all"),
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
    chat_service = ThreadService(current_user.tenant_id, db)
    actor = ActorContext(tenant_id=current_user.tenant_id, user_id=current_user.id, user_role=current_user.role)

    if scope == "shared":
        _require_shared_threads_enabled()
        threads = await chat_service.list_shared_threads_for_user(current_user.id)
    elif scope == "all":
        personal = await chat_service.list_user_threads(current_user.id, agent_id=agent_id, actor=actor)
        shared = (
            await chat_service.list_shared_threads_for_user(current_user.id)
            if EnvConfig.SHARED_THREADS_ENABLED
            else []
        )
        seen = {t.id for t in personal}
        threads = personal + [t for t in shared if t.id not in seen]
    else:
        threads = await chat_service.list_user_threads(current_user.id, agent_id=agent_id, actor=actor)

    return [_thread_response(t) for t in threads]


@router.post("/{thread_id}/messages/compose", response_model=ComposeThreadMessageResponse)
async def compose_thread_message_route(
    thread_id: str,
    request: ComposeThreadMessageRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    mentions = [m.model_dump() for m in request.mentions]
    row, invoke_agent_ids = await compose_thread_message(
        db,
        tenant_id=current_user.tenant_id,
        thread_id=thread_id,
        author=current_user,
        content=request.content,
        mentions=mentions,
        attached_artifact_ids=request.attached_artifact_ids or None,
    )
    await db.commit()
    return ComposeThreadMessageResponse(
        message_id=row.message_id or str(row.id),
        thread_id=row.thread_id,
        content=row.content,
        author_user_id=row.author_user_id or current_user.id,
        created_at=row.created_at,
        invoke_agent_ids=invoke_agent_ids,
    )


@router.post("/{thread_id}/room-messages", response_model=RoomMessageResponse)
async def post_room_message(
    thread_id: str,
    request: RoomMessageCreate,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    _require_shared_threads_enabled()
    row, _invoke = await compose_thread_message(
        db,
        tenant_id=current_user.tenant_id,
        thread_id=thread_id,
        author=current_user,
        content=request.content,
        mentions=[],
        attached_artifact_ids=None,
    )
    await db.commit()
    return RoomMessageResponse(
        message_id=row.message_id or str(row.id),
        thread_id=row.thread_id,
        content=row.content,
        author_user_id=row.author_user_id or current_user.id,
        created_at=row.created_at,
    )


@router.get("/{thread_id}/members", response_model=list[ThreadMemberResponse])
async def list_thread_members(
    thread_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    await require_read_thread(db, thread_id=thread_id, user=current_user)
    members = await ThreadMembershipRepository(db).list_user_members(thread_id)
    names = await usernames_for_user_ids(
        db,
        tenant_id=current_user.tenant_id,
        user_ids=[m.user_id for m in members],
    )
    return [
        ThreadMemberResponse(user_id=m.user_id, role=m.role, username=names.get(m.user_id))
        for m in members
    ]


@router.post("/{thread_id}/members", response_model=ThreadMemberResponse)
async def add_thread_member(
    thread_id: str,
    request: ThreadMemberAdd,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    _require_shared_threads_enabled()
    thread = await require_write_thread(db, thread_id=thread_id, user=current_user)
    membership_repo = ThreadMembershipRepository(db)
    if thread.thread_kind == THREAD_KIND_SHARED:
        actor_membership = await membership_repo.get_user_member(thread_id, current_user.id)
        if actor_membership is None or actor_membership.role != MEMBER_ROLE_OWNER:
            raise AuthorizationError("Only thread owners can add members")
    elif thread.user_id != current_user.id:
        raise AuthorizationError("Only thread owners can add members")
    chat_service = ThreadService(current_user.tenant_id, db)
    added = await chat_service.add_user_member_to_thread(
        thread_id=thread_id,
        owner_user_id=current_user.id,
        user_id=request.user_id,
    )
    if not added:
        raise ResourceNotFoundError(f"Thread {thread_id} not found or not updatable")
    row = await membership_repo.get_user_member(thread_id, request.user_id)
    if row is None:
        raise InternalServiceError("Failed to add member")
    names = await usernames_for_user_ids(
        db,
        tenant_id=current_user.tenant_id,
        user_ids=[row.user_id],
    )
    return ThreadMemberResponse(
        user_id=row.user_id,
        role=row.role,
        username=names.get(row.user_id),
    )


@router.delete("/{thread_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_thread_member(
    thread_id: str,
    user_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    _require_shared_threads_enabled()
    thread = await require_write_thread(db, thread_id=thread_id, user=current_user)
    membership_repo = ThreadMembershipRepository(db)
    if thread.thread_kind == THREAD_KIND_SHARED:
        actor_membership = await membership_repo.get_user_member(thread_id, current_user.id)
        if actor_membership is None or actor_membership.role != MEMBER_ROLE_OWNER:
            raise AuthorizationError("Only thread owners can remove members")
    elif thread.user_id != current_user.id:
        raise AuthorizationError("Only thread owners can remove members")
    target = await membership_repo.get_user_member(thread_id, user_id)
    if target is None:
        return
    if user_id == current_user.id:
        raise AuthorizationError("Cannot remove yourself")
    if target.role == MEMBER_ROLE_OWNER:
        raise AuthorizationError("Cannot remove the thread owner")
    chat_service = ThreadService(current_user.tenant_id, db)
    removed = await chat_service.remove_user_member_from_thread(
        thread_id=thread_id,
        owner_user_id=current_user.id,
        user_id=user_id,
    )
    if not removed:
        raise AuthorizationError("Only thread owners can remove members")


@router.patch("/{thread_id}/members/{user_id}", response_model=ThreadMemberResponse)
async def update_thread_member_role(
    thread_id: str,
    user_id: int,
    request: ThreadMemberRoleUpdate,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    _require_shared_threads_enabled()
    thread = await require_write_thread(db, thread_id=thread_id, user=current_user)
    membership_repo = ThreadMembershipRepository(db)
    if thread.thread_kind == THREAD_KIND_SHARED:
        actor_membership = await membership_repo.get_user_member(thread_id, current_user.id)
        if actor_membership is None or actor_membership.role != MEMBER_ROLE_OWNER:
            raise AuthorizationError("Only thread owners can change member roles")
    elif thread.user_id != current_user.id:
        raise AuthorizationError("Only thread owners can change member roles")
    if user_id == current_user.id:
        raise AuthorizationError("Cannot change your own role")
    chat_service = ThreadService(current_user.tenant_id, db)
    updated = await chat_service.update_user_member_role_on_thread(
        thread_id=thread_id,
        owner_user_id=current_user.id,
        user_id=user_id,
        role=request.role,
    )
    if not updated:
        raise AuthorizationError("Unable to update member role")
    row = await membership_repo.get_user_member(thread_id, user_id)
    if row is None:
        raise InternalServiceError("Failed to load updated member")
    names = await usernames_for_user_ids(
        db,
        tenant_id=current_user.tenant_id,
        user_ids=[row.user_id],
    )
    return ThreadMemberResponse(
        user_id=row.user_id,
        role=row.role,
        username=names.get(row.user_id),
    )


@router.post("/{thread_id}/agents", response_model=ThreadAgentRosterResponse)
async def add_thread_agent(
    thread_id: str,
    request: ThreadAgentAdd,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    _require_shared_threads_enabled()
    thread = await require_write_thread(db, thread_id=thread_id, user=current_user)
    if thread.thread_kind == THREAD_KIND_SHARED:
        membership_repo = ThreadMembershipRepository(db)
        actor_membership = await membership_repo.get_user_member(thread_id, current_user.id)
        if actor_membership is None or actor_membership.role != MEMBER_ROLE_OWNER:
            raise AuthorizationError("Only thread owners can add agents")
    elif thread.user_id != current_user.id:
        raise AuthorizationError("Only thread owners can add agents")
    chat_service = ThreadService(current_user.tenant_id, db)
    added = await chat_service.add_agent_member_to_thread(
        thread_id=thread_id,
        owner_user_id=current_user.id,
        agent_id=request.agent_id,
    )
    if not added:
        raise ResourceNotFoundError(f"Thread {thread_id} not found or not updatable")
    membership_repo = ThreadMembershipRepository(db)
    row = await membership_repo.get_agent_member(thread_id, request.agent_id)
    if row is None:
        raise InternalServiceError("Failed to add agent")
    return ThreadAgentRosterResponse(agent_id=row.agent_id, display_alias=row.display_alias)


@router.get("/{thread_id}/agents", response_model=list[ThreadAgentRosterResponse])
async def list_thread_agent_roster(
    thread_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    await require_read_thread(db, thread_id=thread_id, user=current_user)
    agents = await ThreadMembershipRepository(db).list_agent_members(thread_id)
    return [
        ThreadAgentRosterResponse(agent_id=a.agent_id, display_alias=a.display_alias) for a in agents
    ]


@router.patch("/{thread_id}/agents/{agent_id}", response_model=ThreadAgentRosterResponse)
async def update_thread_agent_primary(
    thread_id: str,
    agent_id: int,
    request: ThreadAgentPrimaryUpdate,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    _require_shared_threads_enabled()
    if not request.is_primary:
        raise ValidationError("Only setting is_primary=true is supported")
    thread = await require_write_thread(db, thread_id=thread_id, user=current_user)
    membership_repo = ThreadMembershipRepository(db)
    if thread.thread_kind == THREAD_KIND_SHARED:
        actor_membership = await membership_repo.get_user_member(thread_id, current_user.id)
        if actor_membership is None or actor_membership.role != MEMBER_ROLE_OWNER:
            raise AuthorizationError("Only thread owners can change agents")
    elif thread.user_id != current_user.id:
        raise AuthorizationError("Only thread owners can change agents")
    chat_service = ThreadService(current_user.tenant_id, db)
    updated = await chat_service.set_primary_agent_on_thread(
        thread_id=thread_id,
        owner_user_id=current_user.id,
        agent_id=agent_id,
    )
    if not updated:
        raise ResourceNotFoundError(f"Agent {agent_id} is not on this thread")
    row = await membership_repo.get_agent_member(thread_id, agent_id)
    if row is None:
        raise InternalServiceError("Failed to load agent roster row")
    return ThreadAgentRosterResponse(agent_id=row.agent_id, display_alias=row.display_alias)


@router.delete("/{thread_id}/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_thread_agent(
    thread_id: str,
    agent_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    _require_shared_threads_enabled()
    thread = await require_write_thread(db, thread_id=thread_id, user=current_user)
    membership_repo = ThreadMembershipRepository(db)
    if thread.thread_kind == THREAD_KIND_SHARED:
        actor_membership = await membership_repo.get_user_member(thread_id, current_user.id)
        if actor_membership is None or actor_membership.role != MEMBER_ROLE_OWNER:
            raise AuthorizationError("Only thread owners can remove agents")
    elif thread.user_id != current_user.id:
        raise AuthorizationError("Only thread owners can remove agents")
    chat_service = ThreadService(current_user.tenant_id, db)
    removed = await chat_service.remove_agent_from_thread(
        thread_id=thread_id,
        owner_user_id=current_user.id,
        agent_id=agent_id,
    )
    if not removed:
        raise ValidationError("Cannot remove the last agent on this conversation")


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
    chat_service = ThreadService(current_user.tenant_id, db)

    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")

    await _assert_user_owns_thread(thread, current_user, db)

    return _thread_response(thread)


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
    chat_service = ThreadService(current_user.tenant_id, db)

    # Verify thread exists and user owns it
    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    await _assert_user_owns_thread(thread, current_user, db)

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
    chat_service = ThreadService(current_user.tenant_id, db)

    # Verify thread exists and user owns it
    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    await _assert_user_owns_thread(thread, current_user, db)

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
    chat_service = ThreadService(current_user.tenant_id, db)

    # Verify thread exists and user owns it
    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    await _assert_user_owns_thread(thread, current_user, db)

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
    chat_service = ThreadService(current_user.tenant_id, db)

    # Verify parent thread exists and user owns it
    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    await _assert_user_owns_thread(thread, current_user, db)
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
    chat_service = ThreadService(current_user.tenant_id, db)

    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    await _assert_user_owns_thread(thread, current_user, db)

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
    chat_service = ThreadService(current_user.tenant_id, db)

    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")
    await _assert_user_owns_thread(thread, current_user, db)

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
    await _assert_user_owns_thread(thread, current_user, db)

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
    await _assert_user_owns_thread(thread, current_user, db)

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
