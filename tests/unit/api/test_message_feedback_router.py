"""Unit tests for message feedback router."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.db.models import Tenant
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.message_feedback.schemas import FeedbackResponse
from apps.tenant_app_service.routers import message_feedback


@pytest.fixture
def app():
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(message_feedback.router)
    return api


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_feedback_service(monkeypatch):
    service = AsyncMock()
    monkeypatch.setattr(
        message_feedback,
        "MessageFeedbackService",
        lambda _tenant_id, _db: service,
    )
    return service


def _feedback_response() -> FeedbackResponse:
    now = datetime.now(UTC)
    return FeedbackResponse(
        message_id="msg_1",
        rating="positive",
        comment=None,
        source="portal",
        created_at=now,
        updated_at=now,
    )


class TestMessageFeedbackRouter:
    def test_upsert_feedback(self, app, client, mock_feedback_service):
        mock_feedback_service.upsert_feedback = AsyncMock(return_value=_feedback_response())

        async def _chat_user():
            return UserDTO(id=1, username="member", role="member", tenant_id=1, tenant_name="t1")

        async def _fake_db():
            yield object()

        app.dependency_overrides[get_current_user] = _chat_user
        app.dependency_overrides[get_db] = _fake_db

        resp = client.put(
            "/threads/thread_1/messages/msg_1/feedback",
            json={"rating": "positive"},
        )
        assert resp.status_code == 200
        assert resp.json()["rating"] == "positive"

    @pytest.mark.asyncio
    async def test_stats_rejects_member(self, app, async_db_session):
        tenant = Tenant(name="tenant_fb", slug="tenant_fb", config=None)
        async_db_session.add(tenant)
        await async_db_session.commit()
        await async_db_session.refresh(tenant)

        async def _member_user():
            return UserDTO(
                id=2,
                username="member",
                role="member",
                tenant_id=tenant.id,
                tenant_name=tenant.name,
            )

        async def _db():
            yield async_db_session

        app.dependency_overrides[get_current_user] = _member_user
        app.dependency_overrides[get_db] = _db

        member_client = TestClient(app)
        resp = member_client.get("/feedback/stats")
        assert resp.status_code == 403

    def test_export_delegates_to_service(self, app, client, mock_feedback_service):
        mock_feedback_service.export_feedback_csv = AsyncMock(return_value="id,thread_id\n1,t1\n")

        async def _admin_user():
            return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")

        async def _fake_db():
            yield object()

        app.dependency_overrides[get_current_user] = _admin_user
        app.dependency_overrides[get_db] = _fake_db

        resp = client.get("/feedback/export")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        mock_feedback_service.export_feedback_csv.assert_awaited_once()
