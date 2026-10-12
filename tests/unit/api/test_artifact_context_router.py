"""Tests for artifact @mention picker API."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from apps.shared.core.auth import get_current_user
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers import artifact_context


@pytest.fixture
def app(monkeypatch):
    application = FastAPI()
    application.include_router(artifact_context.router)

    async def _user():
        return UserDTO(
            id=7,
            username="member",
            role="member",
            tenant_id=1,
            tenant_name="T",
        )

    async def _db():
        yield MagicMock()

    async def _allow_permission(db, user, _permissions):
        return user

    monkeypatch.setattr(
        "apps.shared.core.auth._ensure_permission",
        _allow_permission,
    )
    application.dependency_overrides[get_current_user] = _user
    application.dependency_overrides[get_db] = _db
    return application


@pytest.mark.asyncio
async def test_context_picker_returns_accessible_artifacts(app, monkeypatch):
    mock_artifact = MagicMock()
    mock_artifact.artifact_type = "dashboard"
    mock_artifact.id = 42
    mock_artifact.resource_id = 99
    mock_artifact.url = "/dashboards/99/embed"
    mock_artifact.title = "Sales"
    mock_artifact.artifact_metadata = {}
    mock_artifact.created_at = datetime.now(UTC)
    mock_artifact.owner_user = MagicMock(username="owner")

    mock_repo = MagicMock()
    mock_repo.list_for_user_access = AsyncMock(return_value=[mock_artifact])
    monkeypatch.setattr(
        "apps.tenant_app_service.routers.artifact_context.ArtifactRepository",
        lambda db: mock_repo,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/artifacts/context-picker", params={"query": "sale", "limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == 42
    assert body[0]["artifact_type"] == "dashboard"
    mock_repo.list_for_user_access.assert_awaited_once()
    call_kwargs = mock_repo.list_for_user_access.await_args.kwargs
    assert call_kwargs["tenant_id"] == 1
    assert call_kwargs["user_id"] == 7
    assert call_kwargs["query"] == "sale"
