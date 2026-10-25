"""Integration: tool_result_status / skip metadata from DB through chat APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from jose import jwt
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.db.models import ChatThread, Tenant, TenantMembership, User
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.memory.conversation_memory_manager import ConversationMemoryManager
from apps.tenant_app_service.agents.tool_executor import ToolExecutor
from apps.tenant_app_service.agents.tools import ToolResult
from apps.tenant_app_service.agents.tools.tool_result import (
    SKIP_CODE_KEY,
    TOOL_RESULT_STATUS_KEY,
    ToolResultStatus,
    ToolSkipCode,
    build_persisted_tool_skip_kwargs,
)
from apps.tenant_app_service.chat.thread_service import ThreadService
from apps.tenant_app_service.server import app
from tests.integration.helpers.thread_run_seed import seed_session_run_with_run_messages

pytestmark = pytest.mark.integration

TEST_SECRET_KEY = "test-secret-key"


def _user_dto(*, user_id: int, username: str, role: str, tenant_id: int, tenant_name: str) -> UserDTO:
    return UserDTO(
        id=user_id,
        username=username,
        role=role,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
    )


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


def _tool_status_run_messages(*, tc_ok: str, tc_err: str, tc_skip: str) -> list[dict]:
    return [
        {
            "message_id": f"ai-{uuid4().hex[:8]}",
            "type": "ai",
            "content": "",
            "tool_calls": [
                {"id": tc_ok, "name": "search_documents", "args": {"query": "ok"}, "type": "tool_call"},
                {"id": tc_err, "name": "search_documents", "args": {"query": "err"}, "type": "tool_call"},
                {"id": tc_skip, "name": "search_documents", "args": {"query": "skip"}, "type": "tool_call"},
            ],
        },
        {
            "message_id": f"tool-ok-{uuid4().hex[:6]}",
            "type": "tool",
            "content": '{"markdown":"ok"}',
            "additional_kwargs": {
                TOOL_RESULT_STATUS_KEY: ToolResultStatus.SUCCESS,
                "tool_call_id": tc_ok,
            },
        },
        {
            "message_id": f"tool-err-{uuid4().hex[:6]}",
            "type": "tool",
            "content": "Tool call failed for 'search_documents': synthetic failure",
            "additional_kwargs": {
                TOOL_RESULT_STATUS_KEY: ToolResultStatus.ERROR,
                "tool_call_id": tc_err,
                "tool_error": {"code": "TOOL_EXECUTION_ERROR", "message": "synthetic failure"},
            },
        },
        {
            "message_id": f"tool-skip-{uuid4().hex[:6]}",
            "type": "tool",
            "content": "Skipped: tool call limit reached for this turn",
            "additional_kwargs": {
                **build_persisted_tool_skip_kwargs(ToolSkipCode.TOOL_LIMIT_SIBLING),
                "tool_call_id": tc_skip,
            },
        },
    ]


async def _seed_tool_status_turn(
    session: AsyncSession,
    *,
    tenant_id: int,
    thread: ChatThread,
    session_id: str,
) -> tuple[str, str, str, str]:
    """Returns session_id, tc_ok, tc_err, tc_skip."""
    tc_ok, tc_err, tc_skip = (f"tc-ok-{uuid4().hex[:6]}", f"tc-err-{uuid4().hex[:6]}", f"tc-skip-{uuid4().hex[:6]}")
    await seed_session_run_with_run_messages(
        session,
        tenant_id=tenant_id,
        thread=thread,
        session_id=session_id,
        human_message_id=f"human-{uuid4().hex[:8]}",
        human_content="run tools",
        run_messages=_tool_status_run_messages(tc_ok=tc_ok, tc_err=tc_err, tc_skip=tc_skip),
    )
    return session_id, tc_ok, tc_err, tc_skip


def _tool_message_by_call_id(messages: list, tool_call_id: str) -> dict | None:
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        kwargs = msg.get("additional_kwargs") or {}
        if kwargs.get("tool_call_id") == tool_call_id:
            return msg
    return None


@pytest.mark.asyncio
async def test_thread_service_history_round_trips_tool_result_status(
    pg_async_db_session: AsyncSession,
    sample_tenant_user_thread,
):
    thread, tenant_id, user_id = sample_tenant_user_thread
    session_id = f"sess-tool-status-{uuid4().hex[:8]}"
    session_id, tc_ok, tc_err, tc_skip = await _seed_tool_status_turn(
        pg_async_db_session,
        tenant_id=tenant_id,
        thread=thread,
        session_id=session_id,
    )

    user = _user_dto(
        user_id=user_id,
        username="integ_user",
        role="admin",
        tenant_id=tenant_id,
        tenant_name="Integration Tenant",
    )
    service = ThreadService(tenant_id, pg_async_db_session)
    history = await service.get_conversation_history(
        agent_id=thread.agent_id,
        current_user=user,
        thread_id=thread.id,
        session_id=session_id,
        session_limit=1,
        include_tool_messages=True,
    )

    by_tc = {
        tc_ok: _tool_message_by_call_id([m.model_dump() for m in history.messages], tc_ok),
        tc_err: _tool_message_by_call_id([m.model_dump() for m in history.messages], tc_err),
        tc_skip: _tool_message_by_call_id([m.model_dump() for m in history.messages], tc_skip),
    }
    assert by_tc[tc_ok] is not None
    assert by_tc[tc_ok]["additional_kwargs"][TOOL_RESULT_STATUS_KEY] == ToolResultStatus.SUCCESS

    assert by_tc[tc_err] is not None
    assert by_tc[tc_err]["additional_kwargs"][TOOL_RESULT_STATUS_KEY] == ToolResultStatus.ERROR

    assert by_tc[tc_skip] is not None
    assert by_tc[tc_skip]["additional_kwargs"][TOOL_RESULT_STATUS_KEY] == ToolResultStatus.SKIPPED
    assert by_tc[tc_skip]["additional_kwargs"][SKIP_CODE_KEY] == ToolSkipCode.TOOL_LIMIT_SIBLING


@pytest.mark.asyncio
async def test_thread_service_tool_call_detail_round_trips_status(
    pg_async_db_session: AsyncSession,
    sample_tenant_user_thread,
):
    thread, tenant_id, _user_id = sample_tenant_user_thread
    session_id = f"sess-detail-{uuid4().hex[:8]}"
    session_id, _tc_ok, tc_err, tc_skip = await _seed_tool_status_turn(
        pg_async_db_session,
        tenant_id=tenant_id,
        thread=thread,
        session_id=session_id,
    )

    service = ThreadService(tenant_id, pg_async_db_session)
    err_detail = await service.get_tool_call_detail(
        thread_id=thread.id,
        tool_call_id=tc_err,
        session_id=session_id,
    )
    skip_detail = await service.get_tool_call_detail(
        thread_id=thread.id,
        tool_call_id=tc_skip,
        session_id=session_id,
    )

    assert err_detail is not None
    assert err_detail.additional_kwargs[TOOL_RESULT_STATUS_KEY] == ToolResultStatus.ERROR

    assert skip_detail is not None
    assert skip_detail.additional_kwargs[TOOL_RESULT_STATUS_KEY] == ToolResultStatus.SKIPPED
    assert skip_detail.additional_kwargs[SKIP_CODE_KEY] == ToolSkipCode.TOOL_LIMIT_SIBLING


@pytest.mark.asyncio
async def test_executor_limit_persisted_and_visible_in_history(
    pg_async_db_session: AsyncSession,
    sample_tenant_user_thread,
):
    """ToolExecutor → ConversationMemoryManager → ThreadService history."""
    from apps.tenant_app_service.chat.agent_run_repository import AgentRunRepository

    thread, tenant_id, user_id = sample_tenant_user_thread
    session_id = f"sess-exec-{uuid4().hex[:8]}"
    trigger_id = f"human-{uuid4().hex[:8]}"
    tool_call_id = f"tc-limit-{uuid4().hex[:6]}"

    run = await AgentRunRepository(pg_async_db_session).create_run(
        tenant_id=tenant_id,
        thread_id=thread.id,
        agent_id=thread.agent_id,
        trigger_message_id=trigger_id,
        invoke_index=0,
        session_id=session_id,
    )

    agent_config = MagicMock()
    mock_tool_config = MagicMock()
    mock_tool_config.tool = AsyncMock()
    mock_tool_config.limit = 1
    mock_tool_config.cacheable = False
    mock_tool_config.cache_invalidates = []
    mock_tool_config.result_retention = "transient"
    mock_tool_config.hitl = {}
    agent_config.get_tool_config.return_value = mock_tool_config
    agent_config.has_skills.return_value = False

    executor = ToolExecutor(agent_config, "test_agent")
    config = RunnableConfig(
        configurable={
            "thread_id": thread.id,
            "session_id": session_id,
            "run_id": run.id,
            "db_session": pg_async_db_session,
            "runtime": {
                "tenant": {"tenant_id": tenant_id, "tenant_name": "Integration Tenant", "config": {}},
                "user": {
                    "user_id": user_id,
                    "username": "integ_user",
                    "role": "admin",
                    "tenant_id": tenant_id,
                    "tenant_name": "Integration Tenant",
                },
                "agent_id": thread.agent_id,
                "agent_name": "test",
                "thread_id": thread.id,
                "session_id": session_id,
            },
        }
    )

    first_call = {"id": tool_call_id, "name": "search_documents", "args": {"query": "one"}}
    mock_tool_config.tool.ainvoke.return_value = ToolResult.success("first")
    msg1, counts, _ = await executor.execute_single_tool(first_call, {}, config)
    assert msg1.additional_kwargs[TOOL_RESULT_STATUS_KEY] == ToolResultStatus.SUCCESS

    second_call = {"id": f"{tool_call_id}-2", "name": "search_documents", "args": {"query": "two"}}
    msg2, _, _ = await executor.execute_single_tool(second_call, counts, config)
    assert msg2.additional_kwargs[TOOL_RESULT_STATUS_KEY] == ToolResultStatus.SKIPPED
    assert msg2.additional_kwargs[SKIP_CODE_KEY] == ToolSkipCode.TOOL_LIMIT_EXCEEDED

    mgr = ConversationMemoryManager(
        pg_async_db_session,
        thread.id,
        tenant_id=tenant_id,
        agent_id=thread.agent_id,
        run_id=run.id,
    )
    await mgr.add_messages([msg2], config)

    service = ThreadService(tenant_id, pg_async_db_session)
    detail = await service.get_tool_call_detail(
        thread_id=thread.id,
        tool_call_id=second_call["id"],
        session_id=session_id,
    )
    assert detail is not None
    assert detail.additional_kwargs[TOOL_RESULT_STATUS_KEY] == ToolResultStatus.SKIPPED
    assert detail.additional_kwargs[SKIP_CODE_KEY] == ToolSkipCode.TOOL_LIMIT_EXCEEDED


@pytest_asyncio.fixture
async def tool_status_http_env(pg_container: str):
    """Committed tenant/thread/run rows + HTTP client overrides."""
    test_engine = create_async_engine(pg_container, future=True, poolclass=NullPool)
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
    thread_id = f"thread-tool-status-{suffix}"
    session_id = f"sess-http-{suffix}"
    tc_ok = tc_err = tc_skip = ""

    async with test_session_local() as seed:
        tenant = Tenant(
            name=f"tool-status-tenant-{suffix}",
            slug=f"tool-status-tenant-{suffix}",
            status="active",
        )
        seed.add(tenant)
        await seed.flush()

        owner = User(
            username=f"tool_status_owner_{suffix}",
            email=f"owner_{suffix}@test.local",
            hashed_password="hashed",
            role="admin",
            tenant_id=tenant.id,
            status="active",
        )
        seed.add(owner)
        await seed.flush()
        seed.add(TenantMembership(tenant_id=tenant.id, user_id=owner.id, status="active"))
        await seed.flush()

        thread = ChatThread(
            id=thread_id,
            tenant_id=tenant.id,
            user_id=owner.id,
            agent_id=1,
            title="tool status e2e",
            message_count=0,
        )
        seed.add(thread)
        await seed.flush()

        session_id, tc_ok, tc_err, tc_skip = await _seed_tool_status_turn(
            seed,
            tenant_id=tenant.id,
            thread=thread,
            session_id=session_id,
        )
        await seed.commit()

        token = _token(owner.id, owner.username, owner.role, tenant.id, tenant.name)

    yield {
        "thread_id": thread_id,
        "session_id": session_id,
        "headers": _auth_headers(token),
        "tc_ok": tc_ok,
        "tc_err": tc_err,
        "tc_skip": tc_skip,
    }

    app.dependency_overrides.clear()
    await test_engine.dispose()


def test_http_messages_and_tool_call_detail_expose_tool_result_status(tool_status_http_env: dict):
    client = TestClient(app)
    thread_id = tool_status_http_env["thread_id"]
    session_id = tool_status_http_env["session_id"]
    headers = tool_status_http_env["headers"]

    history = client.get(
        f"/threads/{thread_id}/messages",
        params={"session_limit": 1, "include_tool_messages": True},
        headers=headers,
    )
    assert history.status_code == 200, history.text
    messages = history.json()["messages"]

    skip_msg = _tool_message_by_call_id(messages, tool_status_http_env["tc_skip"])
    err_msg = _tool_message_by_call_id(messages, tool_status_http_env["tc_err"])
    assert skip_msg["additional_kwargs"][TOOL_RESULT_STATUS_KEY] == ToolResultStatus.SKIPPED
    assert err_msg["additional_kwargs"][TOOL_RESULT_STATUS_KEY] == ToolResultStatus.ERROR

    detail = client.get(
        f"/threads/{thread_id}/tool-calls/{tool_status_http_env['tc_skip']}",
        params={"session_id": session_id},
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["additional_kwargs"][TOOL_RESULT_STATUS_KEY] == ToolResultStatus.SKIPPED
    assert body["additional_kwargs"][SKIP_CODE_KEY] == ToolSkipCode.TOOL_LIMIT_SIBLING
