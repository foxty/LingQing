"""Integration tests for agent catalog visibility, sharing, and attachment ACL."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from jose import jwt
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.core.policy_seed import seed_default_policies
from apps.shared.api_connector.domain import RatePolicyDomain
from apps.shared.api_connector.service import ApiConnectorService
from apps.shared.db.models import DataSource, DocumentCollection, Tenant, TenantMembership, User
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_DATA_SOURCE,
    RESOURCE_TYPE_DOCUMENT_COLLECTION,
)
from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID
from apps.tenant_app_service.agents.runtime_capability import build_agent_capability_profile
from apps.tenant_app_service.agents.tools import rag
from apps.tenant_app_service.server import app
from tests.integration.conftest import TEST_SECRET_KEY

pytestmark = pytest.mark.integration


class _SessionContext:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _auth_headers(token: str) -> dict[str, str]:
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


def _agent_create_payload(
    *,
    name: str,
    collection_id: int | None = None,
    data_source_id: int | None = None,
    api_connector_id: int | None = None,
) -> dict:
    tools: list[str] = []
    config: dict = {}
    if collection_id is not None:
        tools.append("search_documents")
        config["knowledge_base_ids"] = [collection_id]
    if data_source_id is not None:
        tools.append("search_data_assets")
        config["data_source_ids"] = [data_source_id]
    if api_connector_id is not None:
        tools.append("search_apis")
        config["api_connector_ids"] = [api_connector_id]
    return {
        "name": name,
        "system_prompt": "Integration test agent.",
        "config": {
            "default_tools": tools,
            **config,
        },
    }


def _full_agent_payload(*, name: str, env: dict) -> dict:
    return _agent_create_payload(
        name=name,
        collection_id=env["collection_id"],
        data_source_id=env["data_source_id"],
        api_connector_id=env["api_connector_id"],
    )


def _attachment_for(body: dict, resource_type: str) -> dict:
    matches = [item for item in body["attachment_access"] if item["resource_type"] == resource_type]
    assert len(matches) == 1, f"expected one {resource_type} attachment, got {matches}"
    return matches[0]


def _share_agent_to_peer(client: TestClient, env: dict, agent_id: int) -> None:
    share_resp = client.post(
        f"/acl-shares/agent/{agent_id}/shares",
        headers=env["owner_headers"],
        json={"user_id": env["peer_id"], "permission": "read"},
    )
    assert share_resp.status_code == 201, share_resp.text


async def _peer_runnable_config(session: AsyncSession, env: dict, *, agent_id: int, agent_name: str) -> RunnableConfig:
    from apps.tenant_app_service.agents.domain import (
        AgentRuntimeContext,
        AgentTenantContext,
        AgentUserContext,
    )

    peer_actor = ActorContext(
        tenant_id=env["tenant_id"],
        user_id=env["peer_id"],
        user_role="member",
    )
    profile = await build_agent_capability_profile(
        session,
        tenant_id=env["tenant_id"],
        actor=peer_actor,
        agent_id=agent_id,
    )
    assert profile is not None
    runtime = AgentRuntimeContext(
        tenant=AgentTenantContext(
            tenant_id=env["tenant_id"],
            tenant_name=env["tenant_name"],
            config={},
        ),
        user=AgentUserContext(
            user_id=env["peer_id"],
            username=env["peer_username"],
            role="member",
            tenant_id=env["tenant_id"],
            tenant_name=env["tenant_name"],
        ),
        agent_id=agent_id,
        agent_name=agent_name,
        thread_id=f"thread-peer-{uuid4().hex[:8]}",
        session_id=f"session-peer-{uuid4().hex[:8]}",
        capability_profile=profile,
    )
    return RunnableConfig(
        configurable={
            "thread_id": runtime.thread_id,
            "runtime": runtime.model_dump(),
        }
    ), profile


@pytest_asyncio.fixture
async def agent_acl_env(async_db_session: AsyncSession):
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
    async with test_session_local() as seed:
        tenant = Tenant(
            name=f"agent-acl-{suffix}",
            slug=f"agent-acl-{suffix}",
            status="active",
        )
        seed.add(tenant)
        await seed.flush()
        await seed_default_policies(seed, tenant.id)

        owner = User(
            username=f"agent_owner_{suffix}",
            email=f"owner_{suffix}@test.local",
            hashed_password="hashed",
            role="member",
            tenant_id=tenant.id,
            status="active",
        )
        peer = User(
            username=f"agent_peer_{suffix}",
            email=f"peer_{suffix}@test.local",
            hashed_password="hashed",
            role="member",
            tenant_id=tenant.id,
            status="active",
        )
        seed.add_all([owner, peer])
        await seed.flush()
        seed.add_all(
            [
                TenantMembership(tenant_id=tenant.id, user_id=owner.id, status="active"),
                TenantMembership(tenant_id=tenant.id, user_id=peer.id, status="active"),
            ]
        )
        collection = DocumentCollection(
            tenant_id=tenant.id,
            name=f"owner-kb-{suffix}",
            description=None,
            owner_id=owner.id,
        )
        data_source = DataSource(
            tenant_id=tenant.id,
            name=f"owner-ds-{suffix}",
            type="postgres",
            managed=True,
            config={
                "host": "localhost",
                "port": 5432,
                "database": "analytics",
                "username": "user",
                "password": "password",
            },
            owner_id=owner.id,
        )
        seed.add_all([collection, data_source])
        await seed.flush()

        connector_service = ApiConnectorService(tenant_id=tenant.id, db_session=seed)
        api_connector = await connector_service.create_connector(
            owner_id=owner.id,
            name=f"owner-api-{suffix}",
            description=None,
            base_url="https://example.com",
            auth_type="none",
            auth_config={},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="manual",
            schema_source_url=None,
        )
        await seed.commit()
        await seed.refresh(owner)
        await seed.refresh(peer)
        await seed.refresh(collection)
        await seed.refresh(data_source)

        owner_token = _make_token(owner.id, owner.username, owner.role, tenant.id, tenant.name)
        peer_token = _make_token(peer.id, peer.username, peer.role, tenant.id, tenant.name)

    env = {
        "tenant_id": tenant.id,
        "tenant_name": tenant.name,
        "owner_id": owner.id,
        "peer_id": peer.id,
        "owner_username": owner.username,
        "peer_username": peer.username,
        "collection_id": collection.id,
        "data_source_id": data_source.id,
        "api_connector_id": api_connector.id,
        "owner_headers": _auth_headers(owner_token),
        "peer_headers": _auth_headers(peer_token),
        "session_local": test_session_local,
    }
    yield env

    app.dependency_overrides.clear()
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_peer_cannot_see_owner_agent_before_share(agent_acl_env):
    client = TestClient(app)
    create_resp = client.post(
        "/agents",
        headers=agent_acl_env["owner_headers"],
        json=_agent_create_payload(
            name=f"Scoped Bot {uuid4().hex[:6]}",
            collection_id=agent_acl_env["collection_id"],
        ),
    )
    assert create_resp.status_code == 201, create_resp.text
    agent_id = create_resp.json()["id"]

    peer_list = client.get("/agents", headers=agent_acl_env["peer_headers"])
    assert peer_list.status_code == 200, peer_list.text
    peer_ids = {item["id"] for item in peer_list.json()}
    assert agent_id not in peer_ids
    assert SYSTEM_AGENT_ONE_ID in peer_ids

    peer_get = client.get(f"/agents/{agent_id}", headers=agent_acl_env["peer_headers"])
    assert peer_get.status_code == 403

    owner_get = client.get(f"/agents/{agent_id}", headers=agent_acl_env["owner_headers"])
    assert owner_get.status_code == 200
    owner_body = owner_get.json()
    kb_items = [
        item
        for item in owner_body["attachment_access"]
        if item["resource_type"] == RESOURCE_TYPE_DOCUMENT_COLLECTION
    ]
    assert len(kb_items) == 1
    assert kb_items[0]["resource_id"] == agent_acl_env["collection_id"]
    assert kb_items[0]["can_read"] is True


@pytest.mark.asyncio
async def test_peer_cannot_create_agent_with_unreadable_collection(agent_acl_env):
    client = TestClient(app)
    resp = client.post(
        "/agents",
        headers=agent_acl_env["peer_headers"],
        json=_agent_create_payload(
            name=f"Peer Steal KB {uuid4().hex[:6]}",
            collection_id=agent_acl_env["collection_id"],
        ),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_peer_cannot_create_agent_with_unreadable_data_source(agent_acl_env):
    client = TestClient(app)
    resp = client.post(
        "/agents",
        headers=agent_acl_env["peer_headers"],
        json=_agent_create_payload(
            name=f"Peer Steal DS {uuid4().hex[:6]}",
            data_source_id=agent_acl_env["data_source_id"],
        ),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_peer_cannot_create_agent_with_unreadable_api_connector(agent_acl_env):
    client = TestClient(app)
    resp = client.post(
        "/agents",
        headers=agent_acl_env["peer_headers"],
        json=_agent_create_payload(
            name=f"Peer Steal API {uuid4().hex[:6]}",
            api_connector_id=agent_acl_env["api_connector_id"],
        ),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_shared_agent_visible_with_attachment_access_gaps(agent_acl_env):
    client = TestClient(app)
    create_resp = client.post(
        "/agents",
        headers=agent_acl_env["owner_headers"],
        json=_agent_create_payload(
            name=f"Shared Bot {uuid4().hex[:6]}",
            collection_id=agent_acl_env["collection_id"],
        ),
    )
    assert create_resp.status_code == 201, create_resp.text
    agent_id = create_resp.json()["id"]

    share_resp = client.post(
        f"/acl-shares/agent/{agent_id}/shares",
        headers=agent_acl_env["owner_headers"],
        json={"user_id": agent_acl_env["peer_id"], "permission": "read"},
    )
    assert share_resp.status_code == 201, share_resp.text

    peer_list = client.get("/agents", headers=agent_acl_env["peer_headers"])
    assert peer_list.status_code == 200
    assert agent_id in {item["id"] for item in peer_list.json()}

    peer_get = client.get(f"/agents/{agent_id}", headers=agent_acl_env["peer_headers"])
    assert peer_get.status_code == 200, peer_get.text
    body = peer_get.json()
    assert body["can_write"] is False
    kb_items = [
        item for item in body["attachment_access"] if item["resource_type"] == RESOURCE_TYPE_DOCUMENT_COLLECTION
    ]
    assert len(kb_items) == 1
    assert kb_items[0]["resource_id"] == agent_acl_env["collection_id"]
    assert kb_items[0]["can_read"] is False

    update_resp = client.put(
        f"/agents/{agent_id}",
        headers=agent_acl_env["peer_headers"],
        json={"name": "Renamed by peer", "system_prompt": "nope", "config": {}},
    )
    assert update_resp.status_code == 403


@pytest.mark.asyncio
async def test_shared_agent_attachment_access_gaps_kb_data_source_and_api(agent_acl_env):
    client = TestClient(app)
    create_resp = client.post(
        "/agents",
        headers=agent_acl_env["owner_headers"],
        json=_full_agent_payload(name=f"Full Attach Bot {uuid4().hex[:6]}", env=agent_acl_env),
    )
    assert create_resp.status_code == 201, create_resp.text
    agent_id = create_resp.json()["id"]

    owner_body = client.get(f"/agents/{agent_id}", headers=agent_acl_env["owner_headers"]).json()
    assert _attachment_for(owner_body, RESOURCE_TYPE_DOCUMENT_COLLECTION)["can_read"] is True
    assert _attachment_for(owner_body, RESOURCE_TYPE_DATA_SOURCE)["can_read"] is True
    assert _attachment_for(owner_body, RESOURCE_TYPE_API_CONNECTOR)["can_read"] is True

    _share_agent_to_peer(client, agent_acl_env, agent_id)

    peer_body = client.get(f"/agents/{agent_id}", headers=agent_acl_env["peer_headers"]).json()
    assert _attachment_for(peer_body, RESOURCE_TYPE_DOCUMENT_COLLECTION)["can_read"] is False
    assert _attachment_for(peer_body, RESOURCE_TYPE_DATA_SOURCE)["can_read"] is False
    assert _attachment_for(peer_body, RESOURCE_TYPE_API_CONNECTOR)["can_read"] is False


@pytest.mark.asyncio
async def test_shared_agent_search_documents_respects_user_acl_not_agent_kb(agent_acl_env, monkeypatch):
    """Peer may invoke a shared agent but document search stays user ACL ∩ agent KB."""
    client = TestClient(app)
    create_resp = client.post(
        "/agents",
        headers=agent_acl_env["owner_headers"],
        json=_agent_create_payload(
            name=f"RAG Bot {uuid4().hex[:6]}",
            collection_id=agent_acl_env["collection_id"],
        ),
    )
    assert create_resp.status_code == 201, create_resp.text
    agent_id = create_resp.json()["id"]

    _share_agent_to_peer(client, agent_acl_env, agent_id)

    async with agent_acl_env["session_local"]() as session:
        monkeypatch.setattr(rag, "app_db_session", lambda: _SessionContext(session))
        config, profile = await _peer_runnable_config(
            session, agent_acl_env, agent_id=agent_id, agent_name="RAG Bot"
        )
        assert profile.allowed_collection_ids == [agent_acl_env["collection_id"]]

        result = await rag.search_documents.ainvoke(
            {"query": "integration", "page": 1, "page_size": 10},
            config=config,
        )
        payload = json.loads(result.content)
        assert payload["total"] == 0
        assert payload["items"] == []


@pytest.mark.asyncio
async def test_shared_agent_search_data_assets_and_apis_respect_user_acl(agent_acl_env, monkeypatch):
    client = TestClient(app)
    create_resp = client.post(
        "/agents",
        headers=agent_acl_env["owner_headers"],
        json=_full_agent_payload(name=f"RAG Full {uuid4().hex[:6]}", env=agent_acl_env),
    )
    assert create_resp.status_code == 201, create_resp.text
    agent_id = create_resp.json()["id"]
    _share_agent_to_peer(client, agent_acl_env, agent_id)

    async with agent_acl_env["session_local"]() as session:
        monkeypatch.setattr(rag, "app_db_session", lambda: _SessionContext(session))
        config, profile = await _peer_runnable_config(
            session, agent_acl_env, agent_id=agent_id, agent_name="RAG Full"
        )
        assert profile.allowed_data_source_ids == [agent_acl_env["data_source_id"]]
        assert profile.allowed_api_connector_ids == [agent_acl_env["api_connector_id"]]

        assets_result = await rag.search_data_assets.ainvoke(
            {"query": "orders", "page": 1, "page_size": 10},
            config=config,
        )
        assets_payload = json.loads(assets_result.content)
        assert assets_payload["total"] == 0
        assert assets_payload["items"] == []

        apis_result = await rag.search_apis.ainvoke(
            {"query": "lookup", "page": 1, "page_size": 10},
            config=config,
        )
        apis_payload = json.loads(apis_result.content)
        assert apis_payload["total"] == 0
        assert apis_payload["items"] == []
