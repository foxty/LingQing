"""Shared helpers for agent tool integration tests."""

from langchain_core.runnables import RunnableConfig

from apps.shared.db.models import Agent, ChatThread, DataSource, User
from tests.integration.helpers.runtime_seed import ensure_runtime_base_records, ensure_runtime_tenant


class SessionContext:
    """Async context manager that reuses fixture session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def patch_agent_tool_db_session(monkeypatch, tool_module, session) -> None:
    """Route agent tool DB access through the integration test session."""

    def _agent_tool_db_session(_config):
        return SessionContext(session)

    monkeypatch.setattr(tool_module, "agent_tool_db_session", _agent_tool_db_session)


async def seed_base_records(async_db_session, runtime_context) -> None:
    await ensure_runtime_base_records(async_db_session, runtime_context)


def postgres_config(async_db_session) -> dict:
    url = async_db_session.bind.engine.url
    return {
        "host": url.host,
        "port": url.port,
        "database": url.database,
        "username": url.username,
        "password": url.password,
    }


async def seed_managed_data_source(async_db_session, runtime_context) -> int:
    ds = DataSource(
        tenant_id=runtime_context.tenant.tenant_id,
        owner_id=runtime_context.user.user_id,
        name="integration_managed_ds",
        type="postgres",
        managed=True,
        config=postgres_config(async_db_session),
    )
    async_db_session.add(ds)
    await async_db_session.commit()
    return int(ds.id)


def build_runnable_config_for_actor(
    runtime_context,
    *,
    user_id: int,
    username: str,
    role: str,
    thread_id: str,
    session_id: str | None = None,
) -> RunnableConfig:
    runtime_payload = runtime_context.model_dump()
    runtime_payload["user"] = {
        **runtime_payload["user"],
        "user_id": user_id,
        "username": username,
        "role": role,
    }
    runtime_payload["thread_id"] = thread_id
    runtime_payload["session_id"] = session_id or f"{runtime_context.session_id}_{user_id}"
    return RunnableConfig(
        configurable={
            "thread_id": thread_id,
            "runtime": runtime_payload,
            "session_id": runtime_payload["session_id"],
        }
    )


async def seed_actor_records(
    async_db_session,
    runtime_context,
    *,
    user_id: int,
    username: str,
    role: str,
    thread_id: str,
) -> None:
    await ensure_runtime_tenant(async_db_session, runtime_context)
    user = await async_db_session.get(User, user_id)
    if user is None:
        user = User(
            id=user_id,
            username=username,
            email=f"{username}@example.com",
            hashed_password="test_password_hash",
            role=role,
            tenant_id=runtime_context.user.tenant_id,
        )
        async_db_session.add(user)
        await async_db_session.flush()

    thread = await async_db_session.get(ChatThread, thread_id)
    if thread is None:
        thread = ChatThread(
            id=thread_id,
            tenant_id=runtime_context.tenant.tenant_id,
            user_id=user_id,
            agent_id=runtime_context.agent_id,
            title=f"{username} thread",
        )
        async_db_session.add(thread)

    await async_db_session.commit()
