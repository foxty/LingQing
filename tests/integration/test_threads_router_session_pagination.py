from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.db.models import ChatThread, Tenant, TenantMembership, User
from apps.tenant_app_service.server import app
from tests.integration.helpers.thread_run_seed import seed_session_run_with_run_messages

TEST_SECRET_KEY = "test-secret-key"


def _make_auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _make_token(user_id: int, username: str, role: str, tenant_id: int, tenant_name: str) -> str:
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
async def thread_session_pagination_setup(async_db_session: AsyncSession):
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

    tenant_suffix = uuid4().hex[:8]
    thread_id = f"thread-session-window-{tenant_suffix}"

    async with test_session_local() as seed_session:
        tenant = Tenant(
            name=f"threads-pagination-tenant-{tenant_suffix}",
            slug=f"threads-pagination-tenant-{tenant_suffix}",
            status="active",
        )
        seed_session.add(tenant)
        await seed_session.flush()

        user = User(
            username=f"threads_user_{tenant_suffix}",
            email=f"threads_{tenant_suffix}@test.local",
            hashed_password="hashed",
            role="admin",
            tenant_id=tenant.id,
            status="active",
        )
        seed_session.add(user)
        await seed_session.flush()

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
            user_id=user.id,
            agent_id=-1,
            title="threads pagination test",
            message_count=7,
        )
        seed_session.add(thread)
        await seed_session.flush()

        base = datetime.now(UTC) - timedelta(hours=2)
        await seed_session_run_with_run_messages(
            seed_session,
            tenant_id=tenant.id,
            thread=thread,
            session_id="sess-1",
            human_message_id=f"{thread_id}-s1-human",
            human_content="session 1 human",
            created_at=base,
            promote_final_ai=True,
            run_messages=[
                {
                    "message_id": f"{thread_id}-s1-ai",
                    "type": "ai",
                    "content": "session 1 ai",
                },
            ],
        )
        await seed_session_run_with_run_messages(
            seed_session,
            tenant_id=tenant.id,
            thread=thread,
            session_id="sess-2",
            human_message_id=f"{thread_id}-s2-human",
            human_content="session 2 human",
            created_at=base + timedelta(minutes=10),
            run_messages=[
                {
                    "message_id": f"{thread_id}-s2-ai",
                    "type": "ai",
                    "content": "session 2 ai",
                    "tool_calls": [{"id": "call-s2", "name": "demo_tool", "args": {}}],
                },
                {
                    "message_id": f"{thread_id}-s2-tool",
                    "type": "tool",
                    "content": "session 2 tool result",
                    "additional_kwargs": {"tool_call_id": "call-s2"},
                },
            ],
        )
        await seed_session_run_with_run_messages(
            seed_session,
            tenant_id=tenant.id,
            thread=thread,
            session_id="sess-3",
            human_message_id=f"{thread_id}-s3-human",
            human_content="session 3 human",
            created_at=base + timedelta(minutes=20),
            promote_final_ai=True,
            run_messages=[
                {
                    "message_id": f"{thread_id}-s3-ai",
                    "type": "ai",
                    "content": "session 3 ai",
                },
            ],
        )

        await seed_session.commit()

        token = _make_token(
            user_id=user.id,
            username=user.username,
            role=user.role,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
        )

    yield {
        "thread_id": thread_id,
        "headers": _make_auth_headers(token),
    }

    app.dependency_overrides.clear()
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_threads_messages_session_window_pagination(thread_session_pagination_setup: dict):
    client = TestClient(app)

    thread_id = thread_session_pagination_setup["thread_id"]
    headers = thread_session_pagination_setup["headers"]

    first_page = client.get(
        f"/threads/{thread_id}/messages",
        params={"session_limit": 2},
        headers=headers,
    )
    assert first_page.status_code == 200, first_page.text
    first_data = first_page.json()

    first_sessions = {message["session_id"] for message in first_data["messages"] if message["session_id"]}
    assert first_sessions == {"sess-2", "sess-3"}
    assert first_data["has_more"] is True
    assert first_data["next_before_session_id"] == "sess-2"
    assert any(message["role"] == "tool" and message["session_id"] == "sess-2" for message in first_data["messages"])

    second_page = client.get(
        f"/threads/{thread_id}/messages",
        params={
            "session_limit": 2,
            "before_session_id": first_data["next_before_session_id"],
        },
        headers=headers,
    )
    assert second_page.status_code == 200, second_page.text
    second_data = second_page.json()

    second_sessions = {message["session_id"] for message in second_data["messages"] if message["session_id"]}
    assert second_sessions == {"sess-1"}
    assert second_data["has_more"] is False
    assert second_data["next_before_session_id"] is None
    assert len(second_data["messages"]) == 2
