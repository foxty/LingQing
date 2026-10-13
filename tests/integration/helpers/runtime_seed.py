"""Idempotent seed helpers for integration tests using ``runtime_context``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import Agent, ChatThread, Tenant, User

if TYPE_CHECKING:
    from apps.tenant_app_service.agents.domain import AgentRuntimeContext


async def ensure_runtime_tenant(session: AsyncSession, runtime_context: AgentRuntimeContext) -> Tenant:
    tenant_id = runtime_context.tenant.tenant_id
    tenant = await session.get(Tenant, tenant_id)
    if tenant is not None:
        return tenant
    tenant = Tenant(
        id=tenant_id,
        name=runtime_context.tenant.tenant_name,
        slug=f"integration-tenant-{tenant_id}",
        status="active",
    )
    session.add(tenant)
    await session.flush()
    return tenant


async def ensure_runtime_user(session: AsyncSession, runtime_context: AgentRuntimeContext) -> User:
    user_id = runtime_context.user.user_id
    user = await session.get(User, user_id)
    if user is not None:
        return user
    user = User(
        id=user_id,
        username=runtime_context.user.username,
        email=f"{runtime_context.user.username}@example.com",
        hashed_password="test_password_hash",
        role=runtime_context.user.role,
        tenant_id=runtime_context.user.tenant_id,
        status="active",
    )
    session.add(user)
    await session.flush()
    return user


async def ensure_runtime_agent(
    session: AsyncSession,
    runtime_context: AgentRuntimeContext,
    *,
    system_prompt: str = "test",
) -> Agent:
    agent_id = runtime_context.agent_id
    agent = await session.get(Agent, agent_id)
    if agent is not None:
        return agent
    agent = Agent(
        id=agent_id,
        tenant_id=runtime_context.tenant.tenant_id,
        owner_id=runtime_context.user.user_id,
        name=runtime_context.agent_name,
        description="test agent",
        system_prompt=system_prompt,
        config={},
        tags=None,
        example_questions=None,
    )
    session.add(agent)
    await session.flush()
    return agent


async def ensure_runtime_thread(
    session: AsyncSession,
    runtime_context: AgentRuntimeContext,
    *,
    thread_id: str | None = None,
    title: str = "test thread",
) -> ChatThread:
    resolved_thread_id = thread_id or runtime_context.thread_id
    thread = await session.get(ChatThread, resolved_thread_id)
    if thread is not None:
        return thread
    thread = ChatThread(
        id=resolved_thread_id,
        tenant_id=runtime_context.tenant.tenant_id,
        user_id=runtime_context.user.user_id,
        agent_id=runtime_context.agent_id,
        title=title,
    )
    session.add(thread)
    await session.flush()
    return thread


async def ensure_runtime_tenant_user(
    session: AsyncSession,
    runtime_context: AgentRuntimeContext,
    *,
    commit: bool = True,
) -> Tenant:
    await ensure_runtime_tenant(session, runtime_context)
    await ensure_runtime_user(session, runtime_context)
    if commit:
        await session.commit()
    tenant = await session.get(Tenant, runtime_context.tenant.tenant_id)
    assert tenant is not None
    return tenant


async def ensure_runtime_base_records(
    session: AsyncSession,
    runtime_context: AgentRuntimeContext,
    *,
    agent_system_prompt: str = "test",
    thread_title: str = "test thread",
    thread_id: str | None = None,
    commit: bool = True,
) -> None:
    """Tenant, user, agent, and thread rows for tool integration tests."""
    await ensure_runtime_tenant(session, runtime_context)
    await ensure_runtime_user(session, runtime_context)
    await ensure_runtime_agent(session, runtime_context, system_prompt=agent_system_prompt)
    await ensure_runtime_thread(
        session,
        runtime_context,
        thread_id=thread_id,
        title=thread_title,
    )
    if commit:
        await session.commit()
