"""Headless chat turn use case (scheduler, background jobs)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import AuthorizationError
from apps.tenant_app_service.auth.adapters import db_user_to_domain, domain_user_to_api
from apps.tenant_app_service.auth.repository import UserRepository
from apps.tenant_app_service.auth.token import JwtTokenIssuer
from apps.tenant_app_service.chat.schemas import ChatRequest, ChatResponse, SimpleMessage
from apps.tenant_app_service.chat.thread_service import ThreadService
from apps.tenant_app_service.chat.turn_sessions import run_non_stream_chat_turn


async def run_headless_chat_turn(
    tenant_id: int,
    db: AsyncSession,
    *,
    user_id: int,
    agent_id: int,
    message: str,
    origin_thread_id: str | None = None,
    task_name: str | None = None,
) -> ChatResponse:
    """Resolve thread + user on ``db``, then run the turn via committed sessions."""
    from apps.tenant_app_service.tenant.repository import TenantRepository

    tenant_repo = TenantRepository(db)
    tenant = await tenant_repo.get_by_id(tenant_id)
    if not tenant:
        raise AuthorizationError(f"Tenant {tenant_id} not found")

    user_repo = UserRepository(db)
    db_user = await user_repo.get_by_id_and_tenant(user_id, tenant_id)
    if not db_user:
        raise AuthorizationError(f"User {user_id} not found in tenant {tenant_id}")

    user_dto = domain_user_to_api(db_user_to_domain(db_user), tenant.name)
    access_token = JwtTokenIssuer().issue(
        user_id=user_dto.id,
        username=user_dto.username,
        role=user_dto.role,
        tenant_id=tenant_id,
        tenant_name=tenant.name,
    )
    thread_id = await _resolve_scheduled_thread_id(
        tenant_id,
        db,
        user_id=user_id,
        agent_id=agent_id,
        message=message,
        origin_thread_id=origin_thread_id,
        task_name=task_name,
    )
    request = ChatRequest(
        tenant_id=tenant_id,
        agent_id=agent_id,
        message=SimpleMessage(role="human", content=message),
        thread_id=thread_id,
    )
    return await run_non_stream_chat_turn(
        tenant_id,
        request,
        user_dto,
        access_token=access_token,
    )


async def _resolve_scheduled_thread_id(
    tenant_id: int,
    db: AsyncSession,
    *,
    user_id: int,
    agent_id: int,
    message: str,
    origin_thread_id: str | None,
    task_name: str | None = None,
) -> str:
    threads = ThreadService(tenant_id, db)
    if origin_thread_id:
        existing = await threads.get_thread(origin_thread_id)
        if existing and existing.tenant_id == tenant_id and existing.user_id == user_id:
            return existing.id

    title_source = task_name or message
    thread = await threads.create_thread(
        user_id=user_id,
        agent_id=agent_id,
        title=title_source[:120],
        first_message=message,
    )
    return thread.id
