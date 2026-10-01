"""Unit tests for admin system tasks router."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.db.session import get_db
from apps.shared.utils.pagination import PaginationRequest
from apps.shared.schemas.user import UserDTO
from apps.shared.tasks.schemas import ScheduledTaskRunResponseDTO, TaskRunResultDTO
from apps.tenant_app_service.routers import admin_system_tasks


@pytest.fixture
def app(monkeypatch):
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(admin_system_tasks.router)

    async def _fake_user():
        return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")

    class _FakeDb:
        async def commit(self):
            return None

    async def _fake_db():
        yield _FakeDb()

    api.dependency_overrides[get_current_user] = _fake_user
    api.dependency_overrides[get_db] = _fake_db

    service = AsyncMock()
    monkeypatch.setattr(
        admin_system_tasks.ScheduledTaskService,
        "create",
        lambda tenant_id, db_session: service,
    )
    api.state.fake_service = service
    return api


@pytest.fixture
def client(app):
    return TestClient(app)


def _sample_system_task():
    return type(
        "Task",
        (),
        {
            "id": 5,
            "tenant_id": 1,
            "name": "Document Parse Worker",
            "task_type": "system",
            "task_config": {"handler_ref": "apps.shared.tasks.system.jobs.document_parse:run_document_parse_jobs"},
            "schedule_type": "cron",
            "schedule_spec": {"cron": "*/2 * * * *", "timezone": "UTC"},
            "status": "pending",
            "next_run_at": datetime.now(UTC),
            "last_run_at": None,
            "error_message": None,
            "notification_channels": None,
            "stable_key": "system.document_parse.poll",
            "execution_mode": "internal",
            "input_params": {},
            "owner_id": 1,
            "user_id": 1,
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        },
    )()


def test_list_system_tasks_returns_payload(client, app):
    app.state.fake_service.list_system_tasks_for_admin = AsyncMock(return_value=[_sample_system_task()])

    resp = client.get("/admin/system-tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["is_system"] is True
    assert data[0]["stable_key"] == "system.document_parse.poll"


def test_list_system_task_runs_returns_pagination(client, app):
    run_dto = ScheduledTaskRunResponseDTO(
        id=42,
        status="success",
        trigger="scheduled",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        duration_ms=100,
        error_message=None,
        result=TaskRunResultDTO(has_logs=False),
    )
    pagination = PaginationRequest.with_total(page=1, page_size=20, total=1)
    app.state.fake_service.list_system_task_runs_for_admin = AsyncMock(return_value=([run_dto], pagination))

    resp = client.get("/admin/system-tasks/5/runs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == 42


def test_pause_system_task(client, app):
    app.state.fake_service.pause_system_task_for_admin = AsyncMock(return_value=True)

    resp = client.patch("/admin/system-tasks/5/pause")
    assert resp.status_code == 200
    assert resp.json()["message"] == "System task paused"


def test_run_system_task_rejects_ineligible(client, app):
    app.state.fake_service.run_system_task_for_admin = AsyncMock(return_value=False)

    resp = client.patch("/admin/system-tasks/5/run")
    assert resp.status_code == 400


def test_run_log_stream_rejects_invalid_value(client, app):
    resp = client.get("/admin/system-tasks/5/runs/42/logs?stream=invalid")
    assert resp.status_code == 422


def test_get_system_task_returns_payload(client, app):
    app.state.fake_service.get_system_task_for_admin = AsyncMock(return_value=_sample_system_task())

    resp = client.get("/admin/system-tasks/5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == 5
    assert data["is_system"] is True
    assert data["stable_key"] == "system.document_parse.poll"


def test_resume_system_task(client, app):
    app.state.fake_service.resume_system_task_for_admin = AsyncMock(return_value=True)

    resp = client.patch("/admin/system-tasks/5/resume")
    assert resp.status_code == 200
    assert resp.json()["message"] == "System task resumed"


def test_resume_system_task_not_found(client, app):
    app.state.fake_service.resume_system_task_for_admin = AsyncMock(return_value=False)

    resp = client.patch("/admin/system-tasks/5/resume")
    assert resp.status_code == 404


def test_get_system_task_run_logs_returns_plain_text(client, app):
    app.state.fake_service.get_system_run_log_content_for_admin = AsyncMock(return_value="line one\nline two\n")

    resp = client.get("/admin/system-tasks/5/runs/42/logs")
    assert resp.status_code == 200
    assert resp.text == "line one\nline two\n"


def test_list_system_tasks_rejects_non_admin(app):
    async def _member_user():
        return UserDTO(id=2, username="member", role="member", tenant_id=1, tenant_name="t1")

    app.dependency_overrides[get_current_user] = _member_user
    member_client = TestClient(app)

    resp = member_client.get("/admin/system-tasks")
    assert resp.status_code == 403
