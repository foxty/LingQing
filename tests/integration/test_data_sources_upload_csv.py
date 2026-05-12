"""Integration slice tests for data sources CSV upload endpoint.

These tests exercise HTTP routing, JWT auth, multipart handling, and router wiring
while mocking service internals that require external analytics DB setup.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.authz import DEFAULT_ROLE_PERMISSIONS
from sqlalchemy import select

from apps.shared.db.models import AssetMetadata, DataSource, Tenant, TenantMembership, User
from apps.tenant_app_service.server import app

TEST_SECRET_KEY = "test-secret-key"


@pytest.fixture
def mock_jwt_token():
    """Create JWT token generator for testing."""
    from jose import jwt

    def _create_token(
        user_id: int,
        username: str,
        role: str,
        tenant_id: int,
        tenant_name: str = "test_tenant",
        expires_delta: timedelta | None = None,
    ) -> str:
        if expires_delta is None:
            expires_delta = timedelta(hours=24)

        expire = datetime.now(timezone.utc) + expires_delta
        to_encode = {
            "user_id": user_id,
            "sub": username,
            "role": role,
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "exp": expire,
        }
        return jwt.encode(to_encode, TEST_SECRET_KEY, algorithm="HS256")

    return _create_token


@pytest_asyncio.fixture
async def upload_csv_test_setup(async_db_session: AsyncSession, mock_jwt_token):
    """Setup tenant/users/tokens, managed data source, and DB override."""
    from apps.shared.db.session import get_db

    session_url = async_db_session.bind.engine.url.render_as_string(hide_password=False)
    url = async_db_session.bind.engine.url
    test_engine = create_async_engine(session_url, future=True, poolclass=NullPool)
    test_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def override_get_db():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    users = {}
    tokens = {}
    async with test_session_factory() as seed_session:
        suffix = uuid4().hex[:8]
        tenant = Tenant(name=f"upload_test_{suffix}", slug=f"upload-test-{suffix}", config=None)
        seed_session.add(tenant)
        await seed_session.flush()

        for role in DEFAULT_ROLE_PERMISSIONS.keys():
            user = User(
                username=f"upload_{role}_{suffix}",
                email=f"upload_{role}_{suffix}@test.local",
                hashed_password="$2b$12$hAjROif0svlKIjI.K5IwGugZ554XGSE44FPpq.1/9ZdSNr23Djvn.",
                tenant_id=tenant.id,
                role=role,
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

            users[role] = user
            tokens[role] = mock_jwt_token(
                user_id=user.id,
                username=user.username,
                role=role,
                tenant_id=tenant.id,
                tenant_name=tenant.name,
            )

        managed_data_source = DataSource(
            tenant_id=tenant.id,
            name=f"upload_ds_{suffix}",
            type="postgres",
            managed=True,
            config={
                "host": url.host,
                "port": url.port,
                "database": url.database,
                "username": url.username,
                "password": url.password,
            },
            owner_id=users["admin"].id,
        )
        seed_session.add(managed_data_source)
        await seed_session.flush()

        await seed_session.commit()

    yield {
        "tenant": tenant,
        "users": users,
        "tokens": tokens,
        "managed_data_source_id": managed_data_source.id,
        "session_factory": test_session_factory,
    }

    app.dependency_overrides.clear()
    await test_engine.dispose()


def make_auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_upload_csv_admin_executes_multipart_flow(upload_csv_test_setup: dict, monkeypatch):
    """Admin can upload CSV end-to-end with real service and DB persistence."""
    client = TestClient(app)
    headers = make_auth_headers(upload_csv_test_setup["tokens"]["admin"])
    data_source_id = upload_csv_test_setup["managed_data_source_id"]

    # Keep integration path real while avoiding external vector infra coupling.
    monkeypatch.setattr("apps.config.EnvConfig.VECTOR_INDEXING_MODE", "async")

    response = client.post(
        f"/data-sources/{data_source_id}/assets/upload-csv",
        headers=headers,
        data={"asset_name": "orders", "description": "integration import"},
        files={"file": ("orders.csv", b"id,name\n1,a\n2,b\n", "text/csv")},
    )

    assert response.status_code == 201, response.text
    assert response.json()["asset_name"] == "orders"
    assert response.json()["row_count"] == 2
    assert response.json()["source_info"]["file_name"] == "orders.csv"

    async with upload_csv_test_setup["session_factory"]() as verify_session:
        result = await verify_session.execute(
            select(AssetMetadata).where(
                AssetMetadata.data_source_id == data_source_id,
                AssetMetadata.asset_name == "orders",
            )
        )
        asset = result.scalar_one_or_none()

    assert asset is not None
    assert asset.owner_id == upload_csv_test_setup["users"]["admin"].id
    assert asset.row_count == 2
    assert asset.source_info.get("file_name") == "orders.csv"


@pytest.mark.asyncio
async def test_upload_csv_rejects_non_csv_file(upload_csv_test_setup: dict):
    """Endpoint should reject non-CSV files at request validation layer."""
    client = TestClient(app)
    headers = make_auth_headers(upload_csv_test_setup["tokens"]["admin"])

    response = client.post(
        f"/data-sources/{upload_csv_test_setup['managed_data_source_id']}/assets/upload-csv",
        headers=headers,
        data={"asset_name": "orders", "description": "should fail"},
        files={"file": ("orders.txt", b"id,name\n1,a\n", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Only CSV files are supported"
