from datetime import datetime, timedelta, timezone

import pytest_asyncio
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.tenant_manager_service.db.models import Base, TenantManagerUser
from apps.tenant_manager_service.db.session import get_tenant_manager_db
from apps.tenant_manager_service.server import app

TEST_SECRET_KEY = "test-secret-key"
TEST_ALGORITHM = "HS256"


def _tm_headers(
    *, role: str, user_id: int = 100, username: str | None = None, scope: str = "tenant-manager"
) -> dict[str, str]:
    payload = {
        "sub": username or f"{role}_user",
        "user_id": user_id,
        "role": role,
        "provider": "native",
        "scope": scope,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    token = jwt.encode(payload, TEST_SECRET_KEY, algorithm=TEST_ALGORITHM)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def tm_auth_db_override():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False, future=True)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, future=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all(
            [
                TenantManagerUser(
                    id=100,
                    username="platform_ops_user",
                    display_name="Platform Ops",
                    password_hash="dummy_hash",
                    role="platform_ops",
                    status="active",
                ),
                TenantManagerUser(
                    id=101,
                    username="inactive_ops_user",
                    display_name="Inactive Ops",
                    password_hash="dummy_hash",
                    role="platform_ops",
                    status="inactive",
                ),
                TenantManagerUser(
                    id=102,
                    username="viewer_user",
                    display_name="Viewer",
                    password_hash="dummy_hash",
                    role="viewer",
                    status="active",
                ),
            ]
        )
        await session.commit()

    async def _override_get_tm_db():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_tenant_manager_db] = _override_get_tm_db
    yield
    app.dependency_overrides.pop(get_tenant_manager_db, None)
    await engine.dispose()


def test_tm_permission_check_requires_authentication(tm_auth_db_override):
    client = TestClient(app)

    response = client.get("/auth/permissions/check")

    assert response.status_code == 401


def test_tm_permission_check_rejects_wrong_scope_token(tm_auth_db_override):
    client = TestClient(app)

    response = client.get("/auth/permissions/check", headers=_tm_headers(role="platform_admin", scope="tenant-app"))

    assert response.status_code == 401
    assert response.json()["message"] == "Invalid token scope"


def test_tm_permission_check_denies_missing_permission_role(tm_auth_db_override):
    client = TestClient(app)

    response = client.get(
        "/auth/permissions/check", headers=_tm_headers(role="viewer", user_id=102, username="viewer_user")
    )

    assert response.status_code == 403
    assert response.json()["message"] == "Insufficient permissions"


def test_tm_permission_check_allows_platform_ops(tm_auth_db_override):
    client = TestClient(app)

    response = client.get("/auth/permissions/check", headers=_tm_headers(role="platform_ops"))

    assert response.status_code == 200
    body = response.json()
    assert body["allowed"] is True
    assert body["role"] == "platform_ops"


def test_tm_permission_check_denies_inactive_user(tm_auth_db_override):
    client = TestClient(app)

    payload = {
        "sub": "inactive_ops_user",
        "user_id": 101,
        "role": "platform_ops",
        "provider": "native",
        "scope": "tenant-manager",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    token = jwt.encode(payload, TEST_SECRET_KEY, algorithm=TEST_ALGORITHM)
    response = client.get("/auth/permissions/check", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["message"] == "User is inactive"


def test_tm_permission_check_denies_token_role_mismatch(tm_auth_db_override):
    client = TestClient(app)

    payload = {
        "sub": "platform_ops_user",
        "user_id": 100,
        "role": "platform_admin",
        "provider": "native",
        "scope": "tenant-manager",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    token = jwt.encode(payload, TEST_SECRET_KEY, algorithm=TEST_ALGORITHM)
    response = client.get("/auth/permissions/check", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 403
    assert response.json()["message"] == "Token role mismatch"
