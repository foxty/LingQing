"""Tests for thread filtering by agent_id."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from apps.shared.core.exceptions import AuthorizationError
from apps.shared.domain.actor import ActorContext
from apps.tenant_app_service.chat.domain import ThreadDomain
from apps.tenant_app_service.chat.repository import ThreadRepository
from apps.tenant_app_service.chat.service import ChatService


@pytest.fixture
def mock_db():
    """Mock database session."""
    return MagicMock()


@pytest.fixture
def thread_repo(mock_db):
    """Create thread repository with mocked DB."""
    return ThreadRepository(mock_db)


@pytest.fixture
def chat_service(mock_db):
    """Create chat service with mocked DB."""
    return ChatService(tenant_id=1, db=mock_db)


@pytest.mark.asyncio
async def test_list_threads_filtered_by_agent_id(chat_service, monkeypatch):
    """Test that list_user_threads properly filters by agent_id."""
    # Mock threads with different agent IDs
    mock_threads = [
        ThreadDomain(
            id="thread1",
            tenant_id=1,
            user_id=1,
            agent_id=-1,  # SYSTEM_AGENT_ONE_ID
            title="Thread 1",
            message_count=5,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        ThreadDomain(
            id="thread2",
            tenant_id=1,
            user_id=1,
            agent_id=10,  # Different agent
            title="Thread 2",
            message_count=3,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
        ThreadDomain(
            id="thread3",
            tenant_id=1,
            user_id=1,
            agent_id=-1,  # SYSTEM_AGENT_ONE_ID
            title="Thread 3",
            message_count=2,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ),
    ]

    async def mock_list_by_user(tenant_id, user_id, limit, agent_id=None):
        if agent_id is None:
            return mock_threads
        return [t for t in mock_threads if t.agent_id == agent_id]

    monkeypatch.setattr(chat_service.thread_repo, "list_by_user", mock_list_by_user)

    # Test without filter - should return all threads
    all_threads = await chat_service.list_user_threads(user_id=1)
    assert len(all_threads) == 3

    # Test with SYSTEM_AGENT_ONE_ID filter - should return only 2 threads
    filtered_threads = await chat_service.list_user_threads(user_id=1, agent_id=-1)
    assert len(filtered_threads) == 2
    assert all(t.agent_id == -1 for t in filtered_threads)
    assert filtered_threads[0].id in ["thread1", "thread3"]
    assert filtered_threads[1].id in ["thread1", "thread3"]

    # Test with different agent_id filter
    other_threads = await chat_service.list_user_threads(user_id=1, agent_id=10)
    assert len(other_threads) == 1
    assert other_threads[0].agent_id == 10
    assert other_threads[0].id == "thread2"


@pytest.mark.asyncio
async def test_list_threads_hides_inaccessible_agents(chat_service, monkeypatch):
    """Inaccessible agents are omitted from the list; a direct filter raises."""
    from types import SimpleNamespace

    now = datetime.now(timezone.utc)
    mock_threads = [
        ThreadDomain(
            id="kept",
            tenant_id=1,
            user_id=1,
            agent_id=-1,
            title="System thread",
            message_count=1,
            created_at=now,
            updated_at=now,
        ),
        ThreadDomain(
            id="revoked",
            tenant_id=1,
            user_id=1,
            agent_id=10,
            title="Revoked agent thread",
            message_count=1,
            created_at=now,
            updated_at=now,
        ),
    ]

    async def mock_list_by_user(tenant_id, user_id, limit, agent_id=None):
        if agent_id is None:
            return mock_threads
        return [t for t in mock_threads if t.agent_id == agent_id]

    class FakeCatalog:
        async def list_agents_for_actor(self, *, actor, assignable_skills=None):
            return [SimpleNamespace(id=-1)]

        async def require_agent_access(self, *, agent_id, actor, action):
            raise AuthorizationError("无权访问该智能体")

    monkeypatch.setattr(chat_service.thread_repo, "list_by_user", mock_list_by_user)
    monkeypatch.setattr(
        "apps.tenant_app_service.agent_catalog.services.AgentCatalogService",
        lambda tenant_id, db_session: FakeCatalog(),
    )

    actor = ActorContext(tenant_id=1, user_id=1, user_role="member")
    visible = await chat_service.list_user_threads(user_id=1, actor=actor)
    assert [t.id for t in visible] == ["kept"]

    with pytest.raises(AuthorizationError):
        await chat_service.list_user_threads(user_id=1, agent_id=10, actor=actor)
