"""Integration tests for durable chat active-run polling and message queries."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.db.models import ChatThread, Tenant, TenantMembership, User
from apps.tenant_app_service.chat.agent_run_domain import AgentRunStatus
from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository
from apps.tenant_app_service.chat.thread_service import ThreadService
from apps.tenant_app_service.server import app
from tests.integration.helpers.committed_chat_setup import seed_running_human_turn
from tests.integration.helpers.thread_run_seed import seed_stale_running_turn

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
async def test_durable_turn_active_run_stale_orphaned_run_repaired_idle(durable_chat_setup: dict):
    thread_id = durable_chat_setup["thread_id"]
    tenant_id = durable_chat_setup["tenant_id"]
    agent_id = durable_chat_setup["agent_id"]
    session_id = f"sess-{uuid4().hex[:8]}"

    async with durable_chat_setup["session_local"]() as db:
        await seed_stale_running_turn(
            db,
            thread_id=thread_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            session_id=session_id,
            stale_minutes=20,
        )
        await db.commit()

        service = ThreadService(tenant_id, db)
        snapshot = await service.get_active_run(thread_id=thread_id, agent_id=agent_id)
        assert snapshot.run_id is None
        assert snapshot.run_status is None


@pytest.mark.asyncio
async def test_durable_turn_active_run_running_then_idle(durable_chat_setup: dict):
    thread_id = durable_chat_setup["thread_id"]
    tenant_id = durable_chat_setup["tenant_id"]
    agent_id = durable_chat_setup["agent_id"]
    session_id = f"sess-{uuid4().hex[:8]}"
    client = TestClient(app)

    async with durable_chat_setup["session_local"]() as db:
        await seed_running_human_turn(
            db,
            thread_id=thread_id,
            agent_id=agent_id,
            session_id=session_id,
            tenant_id=tenant_id,
        )
        await db.commit()

        service = ThreadService(tenant_id, db)
        running = await service.get_active_run(thread_id=thread_id, agent_id=agent_id)
        assert running.run_status == "running"
        assert running.session_id == session_id
        assert running.run_id is not None

    running_http = client.get(
        f"/threads/{thread_id}/active-run",
        headers=durable_chat_setup["owner_headers"],
    )
    assert running_http.status_code == 200, running_http.text
    assert running_http.json()["run_status"] == "running"

    async with durable_chat_setup["session_local"]() as db:
        from apps.tenant_app_service.chat.main_message_repository import MainMessageRepository

        run = await AgentRunRepository(db).get_by_session_id(session_id)
        assert run is not None
        await MainMessageRepository(db).insert_promoted_ai(
            message_id=f"{thread_id}-ai",
            thread_id=thread_id,
            content="response",
            agent_id=agent_id,
            trigger_message_id=run.trigger_message_id,
            agent_run_id=run.id,
            invoke_index=0,
            session_id=session_id,
        )
        await AgentRunRepository(db).set_status(run.id, status=AgentRunStatus.COMPLETED)
        await db.commit()

        service = ThreadService(tenant_id, db)
        completed = await service.get_active_run(thread_id=thread_id, agent_id=agent_id)
        assert completed.run_id is None
        assert completed.run_status is None

    completed_http = client.get(
        f"/threads/{thread_id}/active-run",
        headers=durable_chat_setup["owner_headers"],
    )
    assert completed_http.status_code == 200, completed_http.text
    assert completed_http.json()["run_id"] is None

    history = client.get(
        f"/threads/{thread_id}/messages",
        params={"session_limit": 1, "include_tool_messages": True},
        headers=durable_chat_setup["owner_headers"],
    )
    assert history.status_code == 200, history.text
    roles = {message["role"] for message in history.json()["messages"]}
    assert roles == {"human", "ai"}


def test_active_run_not_found(durable_chat_setup: dict):
    client = TestClient(app)
    missing_id = f"missing-{uuid4().hex[:8]}"
    response = client.get(
        f"/threads/{missing_id}/active-run",
        headers=durable_chat_setup["owner_headers"],
    )
    assert response.status_code == 404


def test_active_run_forbidden_for_non_owner(durable_chat_setup: dict):
    client = TestClient(app)
    response = client.get(
        f"/threads/{durable_chat_setup['thread_id']}/active-run",
        headers=durable_chat_setup["other_headers"],
    )
    assert response.status_code == 403


def test_active_run_idle_for_empty_thread(durable_chat_setup: dict):
    client = TestClient(app)
    response = client.get(
        f"/threads/{durable_chat_setup['thread_id']}/active-run",
        headers=durable_chat_setup["owner_headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["run_id"] is None
    assert body["run_status"] is None
