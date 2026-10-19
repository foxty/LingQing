"""Committed PostgreSQL sessions for chat HTTP integration tests.

``pg_async_db_session`` uses a single outer transaction with savepoints; chat
turn admission and ``app_db_session`` need real commits visible across sessions.
This helper spins a dedicated engine (same URL) and wires ``get_db`` +
``app_db_session`` to committed sessions for the duration of a test.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import pytest_asyncio
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.db.models import ChatThread, Tenant, TenantMembership, User
from apps.shared.db.session import get_db
from apps.tenant_app_service.server import app

TEST_SECRET_KEY = "test-secret-key"


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _issue_token(user_id: int, username: str, role: str, tenant_id: int, tenant_name: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "user_id": user_id,
        "sub": username,
        "role": role,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "exp": expire,
    }
    return jwt.encode(payload, TEST_SECRET_KEY, algorithm="HS256")


def _patch_app_db_session(session_local: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    from apps.shared.core import auth as auth_module
    from apps.shared.db import session as session_module
    from apps.tenant_app_service.chat import turn_sessions as turn_sessions_module
    from apps.tenant_app_service.routers import chat as chat_router_module

    originals = {
        "session_module": session_module.app_db_session,
        "auth": auth_module.app_db_session,
        "chat_router": chat_router_module.app_db_session,
        "turn_sessions": turn_sessions_module.app_db_session,
    }

    @asynccontextmanager
    async def committed_app_db_session():
        async with session_local() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    session_module.app_db_session = committed_app_db_session
    auth_module.app_db_session = committed_app_db_session
    chat_router_module.app_db_session = committed_app_db_session
    turn_sessions_module.app_db_session = committed_app_db_session
    return originals


def _restore_app_db_session(originals: dict[str, Any]) -> None:
    from apps.shared.core import auth as auth_module
    from apps.shared.db import session as session_module
    from apps.tenant_app_service.chat import turn_sessions as turn_sessions_module
    from apps.tenant_app_service.routers import chat as chat_router_module

    session_module.app_db_session = originals["session_module"]
    auth_module.app_db_session = originals["auth"]
    chat_router_module.app_db_session = originals["chat_router"]
    turn_sessions_module.app_db_session = originals["turn_sessions"]


@pytest_asyncio.fixture
async def committed_chat_setup(async_db_session: AsyncSession):
    """Tenant, thread, JWT, and committed DB wiring for chat API tests."""
    session_url = async_db_session.bind.engine.url.render_as_string(hide_password=False)
    test_engine = create_async_engine(session_url, future=True, poolclass=NullPool)
    session_local = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def override_get_db():
        async with session_local() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db
    db_patches = _patch_app_db_session(session_local)

    suffix = uuid4().hex[:8]
    thread_id = f"thread-admission-{suffix}"

    async with session_local() as seed_session:
        tenant = Tenant(
            name=f"admission-tenant-{suffix}",
            slug=f"admission-tenant-{suffix}",
            status="active",
        )
        seed_session.add(tenant)
        await seed_session.flush()

        owner = User(
            username=f"admission_owner_{suffix}",
            email=f"admission_owner_{suffix}@test.local",
            hashed_password="hashed",
            role="admin",
            tenant_id=tenant.id,
            status="active",
        )
        seed_session.add(owner)
        await seed_session.flush()
        seed_session.add(
            TenantMembership(
                tenant_id=tenant.id,
                user_id=owner.id,
                status="active",
            )
        )
        await seed_session.flush()

        thread = ChatThread(
            id=thread_id,
            tenant_id=tenant.id,
            user_id=owner.id,
            agent_id=-1,
            title="admission test",
            message_count=0,
        )
        seed_session.add(thread)
        await seed_session.commit()

        owner_token = _issue_token(owner.id, owner.username, owner.role, tenant.id, tenant.name)

    yield {
        "thread_id": thread_id,
        "tenant_id": tenant.id,
        "agent_id": thread.agent_id,
        "owner_id": owner.id,
        "owner_headers": auth_headers(owner_token),
        "session_local": session_local,
        "pg_url": session_url,
    }

    app.dependency_overrides.clear()
    _restore_app_db_session(db_patches)
    await test_engine.dispose()


async def seed_running_human_turn(
    session: AsyncSession,
    *,
    thread_id: str,
    agent_id: int,
    session_id: str,
    tenant_id: int | None = None,
    user_id: int | None = None,
    content: str = "in-flight user message",
) -> None:
    from apps.shared.db.models import ChatMessage

    if tenant_id is not None and user_id is not None:
        existing = await session.get(ChatThread, thread_id)
        if existing is None:
            session.add(
                ChatThread(
                    id=thread_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_id=agent_id,
                    title="running turn seed",
                    message_count=1,
                )
            )
            await session.flush()

    session.add(
        ChatMessage(
            message_id=f"{thread_id}-human-{uuid4().hex[:6]}",
            thread_id=thread_id,
            type="human",
            content=content,
            session_id=session_id,
            agent_id=agent_id,
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
