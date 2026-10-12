"""Integration tests for artifact @mention picker HTTP + ACL."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.db.models import AclGrant, Artifact, ResourceAcl, Tenant, TenantMembership, User
from apps.shared.db.session import get_db
from apps.tenant_app_service.server import app
from tests.helpers.artifact_access_fixtures import create_standalone_artifact, grant_artifact_acl

TEST_SECRET_KEY = "test-secret-key"


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


@pytest_asyncio.fixture
async def artifact_picker_env(async_db_session: AsyncSession):
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
            name=f"picker-tenant-{suffix}",
            slug=f"picker-tenant-{suffix}",
            status="active",
        )
        seed.add(tenant)
        await seed.flush()

        owner = User(
            username=f"picker_owner_{suffix}",
            email=f"owner_{suffix}@test.local",
            hashed_password="hashed",
            role="member",
            tenant_id=tenant.id,
            status="active",
        )
        peer = User(
            username=f"picker_peer_{suffix}",
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
        await seed.flush()

        owned = Artifact(
            tenant_id=tenant.id,
            artifact_type="report",
            resource_id=9001,
            owner_id=owner.id,
            title="Owner Private Report",
            url="/reports/9001/embed",
            artifact_metadata={},
            source_thread_id=None,
        )
        shared = Artifact(
            tenant_id=tenant.id,
            artifact_type="report",
            resource_id=9002,
            owner_id=owner.id,
            title="Shared Report",
            url="/reports/9002/embed",
            artifact_metadata={},
            source_thread_id=None,
        )
        seed.add_all([owned, shared])
        await seed.flush()

        seed.add(
            ResourceAcl(
                tenant_id=tenant.id,
                resource_type="report",
                resource_id=shared.resource_id,
                owner_id=owner.id,
                status="active",
            )
        )
        seed.add(
            AclGrant(
                tenant_id=tenant.id,
                resource_type="report",
                resource_id=shared.resource_id,
                principal_type="user",
                principal_id=str(peer.id),
                permission="read",
                effect="allow",
                created_by=owner.id,
            )
        )
        await seed.commit()

        owned_id = owned.id
        shared_id = shared.id
        owner_token = _make_token(owner.id, owner.username, owner.role, tenant.id, tenant.name)
        peer_token = _make_token(peer.id, peer.username, peer.role, tenant.id, tenant.name)

    yield {
        "owner_headers": _auth_headers(owner_token),
        "peer_headers": _auth_headers(peer_token),
        "owned_artifact_id": owned_id,
        "shared_artifact_id": shared_id,
    }

    app.dependency_overrides.clear()
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_context_picker_owner_sees_all_own_artifacts(artifact_picker_env):
    client = TestClient(app)
    response = client.get("/artifacts/context-picker", headers=artifact_picker_env["owner_headers"])
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()}
    assert artifact_picker_env["owned_artifact_id"] in ids
    assert artifact_picker_env["shared_artifact_id"] in ids


@pytest.mark.asyncio
async def test_context_picker_peer_sees_only_shared_artifact(artifact_picker_env):
    client = TestClient(app)
    response = client.get("/artifacts/context-picker", headers=artifact_picker_env["peer_headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == artifact_picker_env["shared_artifact_id"]


@pytest.mark.asyncio
async def test_context_picker_query_filters_by_title(artifact_picker_env):
    client = TestClient(app)
    response = client.get(
        "/artifacts/context-picker",
        params={"query": "Shared"},
        headers=artifact_picker_env["owner_headers"],
    )
    assert response.status_code == 200, response.text
    titles = [item["title"] for item in response.json()]
    assert titles == ["Shared Report"]


@pytest.mark.asyncio
async def test_legacy_context_resources_route_removed():
    client = TestClient(app)
    response = client.get("/context-resources/search")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_context_picker_write_share_visible_to_peer(async_db_session: AsyncSession):
    """Peer with write-only ACL grant appears in picker (read permission expansion)."""
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
    try:
        async with test_session_local() as seed:
            tenant = Tenant(
                name=f"write-share-{suffix}",
                slug=f"write-share-{suffix}",
                status="active",
            )
            seed.add(tenant)
            await seed.flush()
            owner = User(
                username=f"w_owner_{suffix}",
                email=None,
                hashed_password="hashed",
                role="member",
                tenant_id=tenant.id,
            )
            peer = User(
                username=f"w_peer_{suffix}",
                email=None,
                hashed_password="hashed",
                role="member",
                tenant_id=tenant.id,
            )
            seed.add_all([owner, peer])
            await seed.flush()
            seed.add_all(
                [
                    TenantMembership(tenant_id=tenant.id, user_id=owner.id, status="active"),
                    TenantMembership(tenant_id=tenant.id, user_id=peer.id, status="active"),
                ]
            )
            await seed.commit()
            await seed.refresh(owner)
            await seed.refresh(peer)

        async with test_session_local() as seed:
            artifact = await create_standalone_artifact(
                seed,
                tenant_id=tenant.id,
                owner_id=owner.id,
                resource_id=9010,
                title="Write Shared",
            )
            await grant_artifact_acl(
                seed,
                tenant_id=tenant.id,
                artifact_type="report",
                resource_id=artifact.resource_id,
                owner_id=owner.id,
                grantee_user_id=peer.id,
                permission="write",
            )
            peer_token = _make_token(peer.id, peer.username, peer.role, tenant.id, tenant.name)

        client = TestClient(app)
        response = client.get("/artifacts/context-picker", headers=_auth_headers(peer_token))
        assert response.status_code == 200, response.text
        assert any(item["title"] == "Write Shared" for item in response.json())
    finally:
        app.dependency_overrides.clear()
        await test_engine.dispose()
