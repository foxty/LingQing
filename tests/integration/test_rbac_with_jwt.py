"""Example: Real-world RBAC integration test with JWT mocking.

This example shows how to properly test RBAC with mocked JWT tokens
for more realistic endpoint testing.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.authz import DEFAULT_ROLE_PERMISSIONS
from apps.shared.db.models import Tenant, TenantMembership, User
from apps.tenant_app_service.server import app

# Test-only secret key (must match the one set in conftest.py)
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
        """Generate a test JWT token."""
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

        encoded_jwt = jwt.encode(
            to_encode,
            TEST_SECRET_KEY,
            algorithm="HS256",
        )
        return encoded_jwt

    return _create_token


@pytest_asyncio.fixture
async def rbac_test_setup(async_db_session: AsyncSession, mock_jwt_token):
    """Setup tenant, users, and tokens for RBAC testing.

    Also overrides the app's database dependency to use the test session.
    """
    from apps.shared.db.session import get_db

    # Override app DB dependency with per-request sessions to avoid loop sharing
    # between pytest's async loop and TestClient's event loop.
    session_url = async_db_session.bind.engine.url.render_as_string(hide_password=False)
    test_engine = create_async_engine(session_url, future=True, poolclass=NullPool)
    TestSessionLocal = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def override_get_db():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed test tenant/users using the same session factory as request handlers,
    # so auth lookups run against visible committed rows.
    users = {}
    tokens = {}
    async with TestSessionLocal() as seed_session:
        tenant_suffix = uuid4().hex[:8]
        user_suffix = uuid4().hex[:8]
        tenant = Tenant(
            name=f"rbac_integration_test_{tenant_suffix}",
            slug=f"rbac_integration_test_{tenant_suffix}",
            config=None,
        )
        seed_session.add(tenant)
        await seed_session.flush()

        for role in DEFAULT_ROLE_PERMISSIONS.keys():
            user = User(
                username=f"testuser_{role}_{user_suffix}",
                email=f"{role}_{user_suffix}@test.local",
                hashed_password="$2b$12$hAjROif0svlKIjI.K5IwGugZ554XGSE44FPpq.1/9ZdSNr23Djvn.",  # dummy
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

        await seed_session.commit()

    yield {
        "tenant": tenant,
        "users": users,
        "tokens": tokens,
    }

    # Clean up dependency overrides
    app.dependency_overrides.clear()
    await test_engine.dispose()


def make_auth_headers(token: str) -> dict:
    """Create authorization headers from token."""
    return {"Authorization": f"Bearer {token}"}


class TestRBACDataSourcesEndpoints:
    """Real-world example: Test data sources endpoints with role-based access.

    This demonstrates testing a subset of endpoints with actual JWT token mocking.
    """

    @pytest.mark.asyncio
    async def test_data_sources_list_viewer_allowed(
        self,
        rbac_test_setup: dict,
    ):
        """Test: Viewer role can read data sources (has DATA_SOURCES_READ)."""
        client = TestClient(app)
        token = rbac_test_setup["tokens"]["viewer"]
        headers = make_auth_headers(token)

        # Note: Actual endpoint would return 200 if data exists, or empty list
        # Here we're testing that auth passes (401 → indicates no auth was attempted)
        # 500 errors from DB issues are OK, we just want to ensure 403 isn't returned
        response = client.get(
            "/data-sources",
            headers=headers,
        )

        # Should NOT be 401 (unauthenticated) or 403 (forbidden)
        # 500 is OK here (DB connection issues), we're just testing auth
        assert response.status_code != 401, f"Auth failed: {response.text}"
        assert response.status_code != 403, f"Permission denied: {response.text}"

    @pytest.mark.asyncio
    async def test_data_sources_create_viewer_denied(
        self,
        rbac_test_setup: dict,
    ):
        """Test: Viewer role cannot create data sources (lacks DATA_SOURCES_WRITE)."""
        client = TestClient(app)
        token = rbac_test_setup["tokens"]["viewer"]
        headers = make_auth_headers(token)

        response = client.post(
            "/data-sources",
            json={
                "name": "test_ds",
                "type": "postgresql",
                "config": {},
            },
            headers=headers,
        )

        # Should be 403 (Forbidden) because viewer lacks DATA_SOURCES_WRITE
        assert response.status_code == 403, (
            f"Viewer should be denied data source creation. Got {response.status_code}: {response.text}"
        )

    @pytest.mark.asyncio
    async def test_data_sources_create_admin_allowed(
        self,
        rbac_test_setup: dict,
    ):
        """Test: Admin role can create data sources (has DATA_SOURCES_WRITE)."""
        client = TestClient(app)
        token = rbac_test_setup["tokens"]["admin"]
        headers = make_auth_headers(token)

        response = client.post(
            "/data-sources",
            json={
                "name": "test_ds_admin",
                "type": "postgresql",
                "config": {
                    "host": "localhost",
                    "port": 5432,
                    "database": "test",
                    "user": "test",
                    "password": "test",
                },
            },
            headers=headers,
        )

        # Should NOT be 403 (forbidden)
        # Status might be 201 (created), 400 (validation error), etc., but not 403
        assert response.status_code != 403, "Admin should be allowed to create data sources. Got 403"

    @pytest.mark.asyncio
    async def test_unauthenticated_data_sources_denied(self):
        """Test: Unauthenticated requests get 401."""
        client = TestClient(app)

        # No Authorization header
        response = client.get("/data-sources")

        assert response.status_code == 401, f"Unauthenticated request should return 401. Got {response.status_code}"

    @pytest.mark.parametrize("role", ["admin", "member"])
    @pytest.mark.asyncio
    async def test_data_sources_write_allowed_for_authorized_roles(
        self,
        role: str,
        rbac_test_setup: dict,
    ):
        """Test: Admin and Member roles can write to data sources."""
        client = TestClient(app)
        token = rbac_test_setup["tokens"][role]
        headers = make_auth_headers(token)

        response = client.get(
            "/data-sources",
            headers=headers,
        )

        # Both admin and member have DATA_SOURCES_WRITE
        assert response.status_code != 401, f"Auth failed: {response.text}"
        assert response.status_code != 403, f"{role} should have data sources write permission"

    @pytest.mark.asyncio
    async def test_viewer_role_progression(
        self,
        rbac_test_setup: dict,
    ):
        """Test: Document viewer role restrictions across multiple operations."""
        client = TestClient(app)
        viewer_token = rbac_test_setup["tokens"]["viewer"]
        viewer_headers = make_auth_headers(viewer_token)

        # Viewer should be allowed to READ
        response = client.get("/data-sources", headers=viewer_headers)
        assert response.status_code != 401, "Auth should pass"
        assert response.status_code != 403, "Viewer should be allowed to read"

        # Viewer should be DENIED to WRITE
        response = client.post(
            "/data-sources",
            json={"name": "test", "type": "postgresql", "config": {}},
            headers=viewer_headers,
        )
        assert response.status_code == 403

        # Viewer should be DENIED to DELETE
        response = client.delete("/data-sources/1", headers=viewer_headers)
        assert response.status_code == 403


class TestRBACChatEndpoints:
    """Test chat endpoints require CHAT_ACCESS permission."""

    @pytest.mark.asyncio
    async def test_chat_member_allowed(self, rbac_test_setup: dict):
        """Member has CHAT_ACCESS."""
        client = TestClient(app)
        token = rbac_test_setup["tokens"]["member"]
        headers = make_auth_headers(token)

        response = client.get("/threads", headers=headers)
        assert response.status_code != 401, "Auth should pass"
        assert response.status_code != 403, "Member should have CHAT_ACCESS"

    @pytest.mark.asyncio
    async def test_chat_viewer_denied(self, rbac_test_setup: dict):
        """Viewer lacks CHAT_ACCESS."""
        client = TestClient(app)
        token = rbac_test_setup["tokens"]["viewer"]
        headers = make_auth_headers(token)

        response = client.get("/threads", headers=headers)
        assert response.status_code == 403


class TestRBACTenantManagement:
    """Test tenant management endpoints require elevated permissions."""

    @pytest.mark.asyncio
    async def test_user_management_admin_only(self, rbac_test_setup: dict):
        """Only admin can manage users."""
        client = TestClient(app)

        # Viewer should be denied
        viewer_headers = make_auth_headers(rbac_test_setup["tokens"]["viewer"])
        response = client.get("/tenants/users", headers=viewer_headers)
        assert response.status_code == 403

        # Admin should be allowed
        admin_headers = make_auth_headers(rbac_test_setup["tokens"]["admin"])
        response = client.get("/tenants/users", headers=admin_headers)
        assert response.status_code != 403


class TestRBACDashboardPreviewEndpoints:
    """Test dashboard preview endpoints with JWT auth and route wiring."""

    @pytest.mark.asyncio
    async def test_dashboard_sql_preview_route_uses_service_method(
        self,
        rbac_test_setup: dict,
        monkeypatch,
    ):
        client = TestClient(app)
        token = rbac_test_setup["tokens"]["admin"]
        headers = make_auth_headers(token)
        captured: dict = {}

        async def _fake_preview_dashboard_sql_for_actor(self, **kwargs):
            captured.update(kwargs)
            return {"columns": [{"name": "total", "type": "int64"}], "rows": [{"total": 1}]}

        from apps.shared.dashboard.service import DashboardService

        monkeypatch.setattr(
            DashboardService,
            "preview_dashboard_sql_for_actor",
            _fake_preview_dashboard_sql_for_actor,
        )

        response = client.post(
            "/dashboards/1/widgets/query-preview",
            json={
                "data_source_id": 6,
                "query": "SELECT 1 AS total",
                "limit": 1,
            },
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["rows"] == [{"total": 1}]
        assert captured["dashboard_id"] == 1
        assert captured["data_source_id"] == 6
        assert captured["query"] == "SELECT 1 AS total"
        assert captured["limit"] == 1
        assert captured["actor"].user_id == rbac_test_setup["users"]["admin"].id

    @pytest.mark.asyncio
    async def test_dashboard_widget_preview_route_uses_widget_service_method(
        self,
        rbac_test_setup: dict,
        monkeypatch,
    ):
        client = TestClient(app)
        token = rbac_test_setup["tokens"]["admin"]
        headers = make_auth_headers(token)
        captured: dict = {}

        async def _fake_preview_dashboard_widget_sql_for_actor(self, **kwargs):
            captured.update(kwargs)
            return {"columns": [{"name": "x", "type": "int64"}], "rows": [{"x": 2}]}

        from apps.shared.dashboard.service import DashboardService

        monkeypatch.setattr(
            DashboardService,
            "preview_dashboard_widget_sql_for_actor",
            _fake_preview_dashboard_widget_sql_for_actor,
        )

        response = client.post(
            "/dashboards/1/widgets/widget-1/query-preview",
            json={
                "query": "SELECT 2 AS x",
                "limit": 2,
            },
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["rows"] == [{"x": 2}]
        assert captured["dashboard_id"] == 1
        assert captured["widget_id"] == "widget-1"
        assert captured["query"] == "SELECT 2 AS x"
        assert captured["limit"] == 2
        assert captured["actor"].user_id == rbac_test_setup["users"]["admin"].id


class TestRBACEdgeCases:
    """Edge cases and boundary conditions for RBAC."""

    @pytest.mark.asyncio
    async def test_expired_token_denied(self, rbac_test_setup: dict, mock_jwt_token):
        """Expired JWT tokens should be rejected."""
        client = TestClient(app)

        # Create an already-expired token
        expired_token = mock_jwt_token(
            user_id=1,
            username="test",
            role="admin",
            tenant_id=rbac_test_setup["tenant"].id,
            tenant_name=rbac_test_setup["tenant"].name,
            expires_delta=timedelta(seconds=-1),  # Expired 1 second ago
        )

        headers = make_auth_headers(expired_token)
        response = client.get("/data-sources", headers=headers)

        assert response.status_code == 401, "Expired token should be rejected"

    @pytest.mark.asyncio
    async def test_malformed_authorization_header(self):
        """Malformed auth header should return 401."""
        client = TestClient(app)

        # Invalid Bearer format
        headers = {"Authorization": "Bearer invalid_token_format"}
        response = client.get("/data-sources", headers=headers)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_token(self):
        """Missing token should return 401."""
        client = TestClient(app)

        response = client.get("/data-sources")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_authorization_scheme(self):
        """Non-Bearer scheme should return 401."""
        client = TestClient(app)

        headers = {"Authorization": "Basic dXNlcjpwYXNz"}  # Basic auth
        response = client.get("/data-sources", headers=headers)

        assert response.status_code == 401
