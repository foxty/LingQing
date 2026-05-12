"""Integration tests for durable chat session status and message queries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.db.models import ChatMessage, ChatThread, Tenant, TenantMembership, User
from apps.tenant_app_service.chat.message_repository import MessageRepository
from apps.tenant_app_service.chat.service import ChatService
from apps.tenant_app_service.server import app

TEST_SECRET_KEY = "test-secret-key"


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(user_id: int, username: str, role: str, tenant_id: int, tenant_name: str) -> str:
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


@pytest_asyncio.fixture
async def durable_chat_setup(async_db_session: AsyncSession):
    from apps.shared.db.session import get_db

    session_url = async_db_session.bind.engine.url.render_as_string(hide_password=False)
    test_engine = create_async_engine(session_url, future=True, poolclass=NullPool)
    test_session_local = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def override_get_db():
        async with test_session_local() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    suffix = uuid4().hex[:8]
    thread_id = f"thread-durable-{suffix}"

    async with test_session_local() as seed_session:
        tenant = Tenant(
            name=f"durable-tenant-{suffix}",
            slug=f"durable-tenant-{suffix}",
            status="active",
        )
        seed_session.add(tenant)
        await seed_session.flush()

        owner = User(
            username=f"durable_owner_{suffix}",
            email=f"durable_owner_{suffix}@test.local",
            hashed_password="hashed",
            role="admin",
            tenant_id=tenant.id,
            status="active",
        )
        other_user = User(
            username=f"durable_other_{suffix}",
            email=f"durable_other_{suffix}@test.local",
            hashed_password="hashed",
            role="admin",
            tenant_id=tenant.id,
            status="active",
        )
        seed_session.add(owner)
        seed_session.add(other_user)
        await seed_session.flush()

        for user in (owner, other_user):
            seed_session.add(
                TenantMembership(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    status="active",
                )
            )
        await seed_session.flush()

        thread = ChatThread(
            id=thread_id,
            tenant_id=tenant.id,
            user_id=owner.id,
            agent_id=-1,
            title="durable chat test",
            message_count=0,
        )
        seed_session.add(thread)
        await seed_session.commit()

        owner_token = _token(owner.id, owner.username, owner.role, tenant.id, tenant.name)
        other_token = _token(other_user.id, other_user.username, other_user.role, tenant.id, tenant.name)

    yield {
        "thread_id": thread_id,
        "tenant_id": tenant.id,
        "agent_id": thread.agent_id,
        "owner_headers": _auth_headers(owner_token),
        "other_headers": _auth_headers(other_token),
        "session_local": test_session_local,
    }

    app.dependency_overrides.clear()
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_message_repository_session_query_helpers(durable_chat_setup: dict):
    thread_id = durable_chat_setup["thread_id"]
    agent_id = durable_chat_setup["agent_id"]
    session_id = f"sess-{uuid4().hex[:8]}"
    baseline = datetime.now(UTC)

    async with durable_chat_setup["session_local"]() as db:
        repo = MessageRepository(db)
        assert await repo.get_latest_human_message(thread_id, agent_id) is None
        assert await repo.has_ai_message_for_session(thread_id, agent_id, session_id) is False

        db.add(
            ChatMessage(
                message_id=f"{thread_id}-human",
                thread_id=thread_id,
                type="human",
                content="hello",
                session_id=session_id,
                agent_id=agent_id,
                created_at=baseline,
            )
        )
        await db.flush()

        latest = await repo.get_latest_human_message(thread_id, agent_id)
        assert latest is not None
        assert latest.session_id == session_id
        assert await repo.has_ai_message_for_session(thread_id, agent_id, session_id) is False

        db.add(
            ChatMessage(
                message_id=f"{thread_id}-ai",
                thread_id=thread_id,
                type="ai",
                content="hi back",
                session_id=session_id,
                agent_id=agent_id,
                created_at=baseline + timedelta(seconds=1),
            )
        )
        await db.flush()

        assert await repo.has_ai_message_for_session(thread_id, agent_id, session_id) is True
        assert await repo.has_messages_after_timestamp(thread_id, agent_id, baseline) is True
        assert (
            await repo.has_messages_after_timestamp(
                thread_id,
                agent_id,
                baseline,
                exclude_session_id=session_id,
            )
            is False
        )


@pytest.mark.asyncio
async def test_durable_turn_session_status_stale_orphaned_run_returns_completed(durable_chat_setup: dict):
    thread_id = durable_chat_setup["thread_id"]
    tenant_id = durable_chat_setup["tenant_id"]
    agent_id = durable_chat_setup["agent_id"]
    session_id = f"sess-{uuid4().hex[:8]}"
    stale_created_at = datetime.now(UTC) - timedelta(minutes=20)

    async with durable_chat_setup["session_local"]() as db:
        db.add(
            ChatMessage(
                message_id=f"{thread_id}-stale-human",
                thread_id=thread_id,
                type="human",
                content="hello",
                session_id=session_id,
                agent_id=agent_id,
                created_at=stale_created_at,
            )
        )
        await db.commit()

        service = ChatService(tenant_id, db)
        status = await service.get_session_status(thread_id=thread_id, agent_id=agent_id)
        assert status.status == "completed"
        assert status.has_ai_response is False


@pytest.mark.asyncio
async def test_durable_turn_session_status_running_then_completed(durable_chat_setup: dict):
    thread_id = durable_chat_setup["thread_id"]
    tenant_id = durable_chat_setup["tenant_id"]
    agent_id = durable_chat_setup["agent_id"]
    session_id = f"sess-{uuid4().hex[:8]}"
    client = TestClient(app)

    async with durable_chat_setup["session_local"]() as db:
        db.add(
            ChatMessage(
                message_id=f"{thread_id}-human",
                thread_id=thread_id,
                type="human",
                content="hello",
                session_id=session_id,
                agent_id=agent_id,
            )
        )
        await db.commit()

        service = ChatService(tenant_id, db)
        running = await service.get_session_status(thread_id=thread_id, agent_id=agent_id)
        assert running.status == "running"
        assert running.session_id == session_id
        assert running.has_ai_response is False

    running_http = client.get(
        f"/threads/{thread_id}/session-status",
        headers=durable_chat_setup["owner_headers"],
    )
    assert running_http.status_code == 200, running_http.text
    assert running_http.json()["status"] == "running"

    async with durable_chat_setup["session_local"]() as db:
        db.add(
            ChatMessage(
                message_id=f"{thread_id}-ai",
                thread_id=thread_id,
                type="ai",
                content="response",
                session_id=session_id,
                agent_id=agent_id,
            )
        )
        await db.commit()

        service = ChatService(tenant_id, db)
        completed = await service.get_session_status(thread_id=thread_id, agent_id=agent_id)
        assert completed.status == "completed"
        assert completed.has_ai_response is True

    completed_http = client.get(
        f"/threads/{thread_id}/session-status",
        headers=durable_chat_setup["owner_headers"],
    )
    assert completed_http.status_code == 200, completed_http.text
    assert completed_http.json()["status"] == "completed"

    history = client.get(
        f"/threads/{thread_id}/messages",
        params={"session_limit": 1, "include_tool_messages": True},
        headers=durable_chat_setup["owner_headers"],
    )
    assert history.status_code == 200, history.text
    roles = {message["role"] for message in history.json()["messages"]}
    assert roles == {"human", "ai"}


def test_session_status_not_found(durable_chat_setup: dict):
    client = TestClient(app)
    missing_id = f"missing-{uuid4().hex[:8]}"
    response = client.get(
        f"/threads/{missing_id}/session-status",
        headers=durable_chat_setup["owner_headers"],
    )
    assert response.status_code == 404


def test_session_status_forbidden_for_non_owner(durable_chat_setup: dict):
    client = TestClient(app)
    response = client.get(
        f"/threads/{durable_chat_setup['thread_id']}/session-status",
        headers=durable_chat_setup["other_headers"],
    )
    assert response.status_code == 403


def test_session_status_completed_for_empty_thread(durable_chat_setup: dict):
    client = TestClient(app)
    response = client.get(
        f"/threads/{durable_chat_setup['thread_id']}/session-status",
        headers=durable_chat_setup["owner_headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
