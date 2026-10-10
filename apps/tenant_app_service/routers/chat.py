"""Chat router."""

from dataclasses import asdict
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission, require_permission_released, security
from apps.shared.core.exceptions import (
    AuthorizationError,
    ResourceNotFoundError,
    ValidationError,
)
from apps.shared.db.session import app_db_session, get_db
from apps.shared.observability.service import ObservabilityService
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.chat import ChatService
from apps.tenant_app_service.chat.adapters import chat_thread_to_domain
from apps.tenant_app_service.chat.domain import ThreadDomain
from apps.tenant_app_service.chat.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


async def _validate_and_get_thread(
    thread_id: str,
    current_user: UserDTO,
    db: AsyncSession,
) -> ThreadDomain:
    """Validate thread_id is provided and accessible.

    Args:
        thread_id: Thread ID to validate
        current_user: Current authenticated user
        db: Database session

    Returns:
        Validated thread_id

    Raises:
        HTTPException: If thread_id is missing, invalid or user doesn't have access
    """
    if not thread_id:
        raise ValidationError("thread_id is required. Please create a thread first.")

    chat_service = ChatService(current_user.tenant_id, db)

    thread = await chat_service.get_thread(thread_id)
    if not thread:
        raise ResourceNotFoundError(f"Thread {thread_id} not found")

    if thread.tenant_id != current_user.tenant_id or thread.user_id != current_user.id:
        raise AuthorizationError(f"Access denied. Thread {thread_id} does not belong to you")

    return chat_thread_to_domain(thread)


@router.post("", response_model=ChatResponse, summary="Chat with an agent")
async def chat(
    request: ChatRequest,
    # Do not use Depends(get_db) or Depends(require_permission()) here.
    # FastAPI keeps a yielded get_db session open until the response is sent,
    # and this handler waits on the agent. require_permission_released()
    # authenticates in a short app_db_session and closes it first.
    current_user: UserDTO = Depends(require_permission_released(Permissions.CHAT_ACCESS)),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Chat with an agent (non-streaming)."""
    # Ensure user can only access their own tenant
    if request.tenant_id != current_user.tenant_id:
        raise AuthorizationError(f"Access denied. You can only access tenant: {current_user.tenant_id}")

    # Agent invoke still needs a session for memory/HITL. Use one short-lived
    # app_db_session for validate + invoke instead of Depends(get_db).
    async with app_db_session() as db:
        await _validate_and_get_thread(request.thread_id, current_user, db)
        chat_service = ChatService(current_user.tenant_id, db)
        return await chat_service.chat(request, current_user, access_token=credentials.credentials)


async def _stream_chat_events(
    request: ChatRequest,
    current_user: UserDTO,
    access_token: str | None,
) -> AsyncIterator[str]:
    """Validate and persist setup, then stream without holding that session."""
    async with app_db_session() as db:
        await _validate_and_get_thread(request.thread_id, current_user, db)
        chat_service = ChatService(current_user.tenant_id, db)
        prepared = await chat_service.prepare_chat_stream(
            request, current_user, access_token=access_token
        )
    async for item in chat_service.iter_prepared_chat_stream(
        request, current_user, prepared, access_token=access_token
    ):
        yield item


@router.post("/stream", include_in_schema=False)
async def chat_stream(
    request: ChatRequest,
    # Do not use Depends(get_db) or Depends(require_permission()) here.
    # FastAPI keeps a yielded get_db session open until the SSE stream ends.
    # require_permission_released() closes auth before this handler runs.
    # Setup uses a short app_db_session inside _stream_chat_events; the agent
    # run opens its own session. The request does not pin the pool during SSE.
    current_user: UserDTO = Depends(require_permission_released(Permissions.CHAT_ACCESS)),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Chat with an agent (streaming)."""
    # Ensure user can only access their own tenant
    if request.tenant_id != current_user.tenant_id:
        raise AuthorizationError(f"Access denied. You can only access tenant: {current_user.tenant_id}")

    return StreamingResponse(
        _stream_chat_events(request, current_user, credentials.credentials),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@router.get("/metrics/session/{session_id}", response_model=dict[str, Any], include_in_schema=False)
async def get_session_metrics(
    session_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated metrics for a chat session.

    Args:
        session_id: Session ID to query
        current_user: Current authenticated user
        db: Database session

    Returns:
        Session metrics including tokens, duration, call counts

    Raises:
        HTTPException: If session not found or unauthorized
    """
    obs_service = ObservabilityService.create(db, current_user.tenant_id)
    metrics = await obs_service.get_session_metrics(session_id)

    if not metrics:
        raise ResourceNotFoundError(f"Session {session_id} not found")

    return asdict(metrics)


@router.get("/metrics/session/{session_id}/tools", response_model=list[dict[str, Any]], include_in_schema=False)
async def get_session_tool_calls(
    session_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Get all tool call metrics for a session.

    Args:
        session_id: Session ID to query
        current_user: Current authenticated user
        db: Database session

    Returns:
        List of tool call metrics

    Raises:
        HTTPException: If session not found or unauthorized
    """
    obs_service = ObservabilityService.create(db, current_user.tenant_id)
    tool_calls = await obs_service.get_session_tool_calls(session_id)

    return tool_calls


@router.get("/metrics/tool/{tool_call_id}", response_model=dict[str, Any], include_in_schema=False)
async def get_tool_call_metrics(
    tool_call_id: str,
    session_id: str,
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
):
    """Get metrics for a specific tool call.

    Args:
        tool_call_id: Tool call ID to query
        session_id: Session ID (required for scoping)
        current_user: Current authenticated user
        db: Database session

    Returns:
        Tool call metrics

    Raises:
        HTTPException: If tool call not found or unauthorized
    """
    obs_service = ObservabilityService.create(db, current_user.tenant_id)
    metrics = await obs_service.get_tool_call_metrics(session_id, tool_call_id)

    if not metrics:
        raise ResourceNotFoundError(f"Tool call {tool_call_id} not found in session {session_id}")

    return metrics
