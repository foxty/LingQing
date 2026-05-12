from __future__ import annotations

from uuid import uuid4

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.shared.api_connector.domain import RatePolicyDomain
from apps.shared.api_connector.service import ApiConnectorService
from apps.shared.authz.authz_query_builder import AuthzSqlFilter
from apps.shared.core.auth import get_current_user
from apps.shared.db.models import Tenant, User
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO
from apps.shared.search.search_service import SearchService
from apps.shared.utils.pagination import PaginationRequest
from apps.tenant_app_service.server import app


@pytest_asyncio.fixture
async def search_api_connector_env(async_db_session: AsyncSession):
    session_url = async_db_session.bind.engine.url.render_as_string(hide_password=False)
    test_engine = create_async_engine(session_url, future=True, poolclass=NullPool)
    test_session_local = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with test_session_local() as schema_session:
        # Integration tests may run against metadata-created schema before latest migrations.
        # Add persisted FTS column/index defensively for API operation search queries.
        await schema_session.execute(
            text(
                """
                ALTER TABLE api_operation_index
                ADD COLUMN IF NOT EXISTS search_vector tsvector
                GENERATED ALWAYS AS (
                    setweight(to_tsvector('english', coalesce(operation_id, '')), 'A') ||
                    setweight(to_tsvector('simple', coalesce(operation_id, '')), 'A') ||
                    setweight(to_tsvector('simple', coalesce(method, '')), 'A') ||
                    setweight(to_tsvector('english', coalesce(summary, '')), 'B') ||
                    setweight(to_tsvector('simple', coalesce(summary, '')), 'B') ||
                    setweight(to_tsvector('english', coalesce(description, '')), 'C') ||
                    setweight(to_tsvector('simple', coalesce(description, '')), 'C') ||
                    setweight(to_tsvector('simple', coalesce(path_template, '')), 'B') ||
                    setweight(to_tsvector('simple', coalesce(tags::text, '')), 'D')
                ) STORED
                """
            )
        )
        await schema_session.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_api_operation_search_vector
                ON api_operation_index USING GIN(search_vector)
                """
            )
        )
        await schema_session.commit()

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

    suffix = uuid4().hex[:8]
    async with test_session_local() as seed_session:
        tenant_a = Tenant(name=f"search-it-a-{suffix}", slug=f"search-it-a-{suffix}", status="active")
        tenant_b = Tenant(name=f"search-it-b-{suffix}", slug=f"search-it-b-{suffix}", status="active")
        seed_session.add_all([tenant_a, tenant_b])
        await seed_session.flush()

        user_a = User(
            username=f"search_user_a_{suffix}",
            email=f"search_a_{suffix}@test.local",
            hashed_password="hashed",
            role="admin",
            tenant_id=tenant_a.id,
            status="active",
        )
        user_b = User(
            username=f"search_user_b_{suffix}",
            email=f"search_b_{suffix}@test.local",
            hashed_password="hashed",
            role="admin",
            tenant_id=tenant_b.id,
            status="active",
        )
        seed_session.add_all([user_a, user_b])
        await seed_session.flush()

        service_a = ApiConnectorService(tenant_id=tenant_a.id, db_session=seed_session)
        service_b = ApiConnectorService(tenant_id=tenant_b.id, db_session=seed_session)

        connector_a = await service_a.create_connector(
            owner_id=user_a.id,
            name="search-router-a",
            description=None,
            base_url="https://8.8.8.8",
            auth_type="none",
            auth_config={},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="manual",
            schema_source_url=None,
        )
        connector_b = await service_b.create_connector(
            owner_id=user_b.id,
            name="search-router-b",
            description=None,
            base_url="https://8.8.8.8",
            auth_type="none",
            auth_config={},
            rate_policy=RatePolicyDomain.from_raw({}),
            schema_source_type="manual",
            schema_source_url=None,
        )

        await service_a.add_manual_operation_for_actor(
            connector_id=connector_a.id,
            actor=ActorContext(tenant_id=tenant_a.id, user_id=user_a.id, user_role=user_a.role),
            method="GET",
            path_template="/orders/a/{id}",
            operation_id="alpha_lookup_primary",
            summary="alpha lookup primary",
            description=None,
            tags=["alpha"],
            request_schema={"type": "object"},
            response_schema={"type": "object"},
        )
        await service_a.add_manual_operation_for_actor(
            connector_id=connector_a.id,
            actor=ActorContext(tenant_id=tenant_a.id, user_id=user_a.id, user_role=user_a.role),
            method="GET",
            path_template="/orders/a/secondary/{id}",
            operation_id="alpha_lookup_secondary",
            summary="alpha lookup secondary",
            description=None,
            tags=["alpha"],
            request_schema={"type": "object"},
            response_schema={"type": "object"},
        )
        await service_b.add_manual_operation_for_actor(
            connector_id=connector_b.id,
            actor=ActorContext(tenant_id=tenant_b.id, user_id=user_b.id, user_role=user_b.role),
            method="GET",
            path_template="/orders/b/{id}",
            operation_id="beta_lookup",
            summary="beta lookup",
            description=None,
            tags=["beta"],
            request_schema={"type": "object"},
            response_schema={"type": "object"},
        )

        await seed_session.commit()

        # Sync resource_index records to populate tokenized_content for FTS
        from apps.shared.search.indexing_service import ResourceIndexService

        indexing_svc_a = ResourceIndexService(tenant_id=tenant_a.id, db_session=seed_session)
        await indexing_svc_a.sync_all_pending()

        indexing_svc_b = ResourceIndexService(tenant_id=tenant_b.id, db_session=seed_session)
        await indexing_svc_b.sync_all_pending()

    user_ctx = {
        "value": UserDTO(
            id=user_a.id,
            username=user_a.username,
            role=user_a.role,
            tenant_id=tenant_a.id,
            tenant_name=tenant_a.name,
        )
    }

    async def override_user():
        return user_ctx["value"]

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_user

    def set_user(dto: UserDTO) -> None:
        user_ctx["value"] = dto

    env = {
        "client": TestClient(app),
        "set_user": set_user,
        "user_a": UserDTO(
            id=user_a.id,
            username=user_a.username,
            role=user_a.role,
            tenant_id=tenant_a.id,
            tenant_name=tenant_a.name,
        ),
        "user_b": UserDTO(
            id=user_b.id,
            username=user_b.username,
            role=user_b.role,
            tenant_id=tenant_b.id,
            tenant_name=tenant_b.name,
        ),
    }

    yield env

    app.dependency_overrides.clear()
    await test_engine.dispose()


def test_search_api_connector_contract(search_api_connector_env, monkeypatch):
    client = search_api_connector_env["client"]

    async def _mock_api_connector_authz_filter(self):
        return AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)

    monkeypatch.setattr(SearchService, "_get_api_connector_authz_filter", _mock_api_connector_authz_filter)

    resp = client.get(
        "/search",
        params={"query": "alpha_lookup_primary", "sources": "api_connector", "page": 1, "page_size": 10},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert all(item["resource_type"] == "api_connector" for item in payload["items"])
    assert all(isinstance(item.get("score"), (int, float)) for item in payload["items"])
    connector_names = [item["contents"][0]["connector_name"] for item in payload["items"]]
    assert "search-router-a" in connector_names


def test_search_api_connector_tenant_isolation(search_api_connector_env, monkeypatch):
    client = search_api_connector_env["client"]
    search_api_connector_env["set_user"](search_api_connector_env["user_b"])

    async def _mock_api_connector_authz_filter(self):
        return AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)

    monkeypatch.setattr(SearchService, "_get_api_connector_authz_filter", _mock_api_connector_authz_filter)

    resp = client.get(
        "/search",
        params={"query": "alpha_lookup_primary", "sources": "api_connector", "page": 1, "page_size": 10},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert all(item["resource_type"] == "api_connector" for item in payload["items"])
    connector_names = [item["contents"][0]["connector_name"] for item in payload["items"]]
    assert "search-router-a" not in connector_names


def test_search_both_includes_api_connector_hits(search_api_connector_env, monkeypatch):
    client = search_api_connector_env["client"]

    async def _mock_search_documents(self, query: str, page: int, page_size: int):
        return [], PaginationRequest(page=page, page_size=page_size, total=0)

    async def _mock_search_assets(self, query: str, page: int, page_size: int):
        return [], PaginationRequest(page=page, page_size=page_size, total=0)

    async def _mock_api_connector_authz_filter(self):
        return AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)

    monkeypatch.setattr(SearchService, "search_documents", _mock_search_documents)
    monkeypatch.setattr(SearchService, "search_assets", _mock_search_assets)
    monkeypatch.setattr(SearchService, "_get_api_connector_authz_filter", _mock_api_connector_authz_filter)

    resp = client.get(
        "/search",
        params={
            "query": "alpha_lookup_primary",
            "sources": ["document", "asset", "api_connector"],
            "page": 1,
            "page_size": 10,
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert any(item["resource_type"] == "api_connector" for item in payload["items"])
    api_items = [item for item in payload["items"] if item["resource_type"] == "api_connector"]
    assert all(isinstance(item.get("score"), (int, float)) for item in api_items)


def test_search_api_connector_respects_page_size(search_api_connector_env, monkeypatch):
    client = search_api_connector_env["client"]

    async def _mock_api_connector_authz_filter(self):
        return AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)

    monkeypatch.setattr(SearchService, "_get_api_connector_authz_filter", _mock_api_connector_authz_filter)

    resp = client.get(
        "/search",
        params={"query": "alpha_lookup", "sources": "api_connector", "page": 1, "page_size": 1},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] >= 1
    assert payload["page"] == 1
    assert payload["page_size"] == 1
    assert len(payload["items"]) == 1
    assert payload["items"][0]["resource_type"] == "api_connector"


def test_search_rejects_invalid_sources(search_api_connector_env):
    client = search_api_connector_env["client"]

    resp = client.get(
        "/search",
        params={"query": "alpha_lookup", "sources": "invalid_target", "page": 1, "page_size": 10},
    )

    assert resp.status_code == 400
    assert "Invalid sources" in resp.json()["detail"]


def test_search_rejects_page_exceed_max(search_api_connector_env):
    client = search_api_connector_env["client"]

    resp = client.get(
        "/search",
        params={"query": "alpha_lookup", "sources": "api_connector", "page": 6, "page_size": 10},
    )

    assert resp.status_code == 422


def test_search_rejects_document_page_size_over_cap(search_api_connector_env):
    client = search_api_connector_env["client"]

    resp = client.get(
        "/search",
        params={"query": "alpha_lookup", "sources": "document", "page": 1, "page_size": 11},
    )

    assert resp.status_code == 400
    assert "page_size exceeds max" in resp.json()["detail"]
