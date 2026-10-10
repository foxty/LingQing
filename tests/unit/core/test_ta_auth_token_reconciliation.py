"""Tenant-app JWT reconciliation with DB user and tenant records."""

from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO


class _FakeMembershipResult:
    def scalar_one_or_none(self):
        return SimpleNamespace(status="active")


class _FakeDb:
    async def execute(self, _stmt):
        return _FakeMembershipResult()


async def _fake_db():
    yield _FakeDb()


def _token_payload(*, role: str = "admin", tenant_name: str = "t9"):
    return {
        "user_id": 7,
        "sub": "u1",
        "role": role,
        "tenant_id": 9,
        "tenant_name": tenant_name,
    }


def _db_user(*, role: str = "admin"):
    return SimpleNamespace(
        tenant_id=9,
        username="u1",
        role=role,
        preferences={},
        status="active",
    )


def _tenant():
    return SimpleNamespace(id=9, name="t9")


def test_get_current_user_rejects_stale_role(monkeypatch):
    async def _fake_get_by_id(self, record_id: int):
        if record_id == 7:
            return _db_user(role="viewer")
        if record_id == 9:
            return _tenant()
        return None

    monkeypatch.setattr("apps.shared.core.auth.jwt.decode", lambda *args, **kwargs: _token_payload(role="admin"))
    monkeypatch.setattr("apps.shared.core.auth.BaseRepository.get_by_id", _fake_get_by_id)

    app = FastAPI()
    app.dependency_overrides[get_db] = _fake_db

    @app.get("/me")
    async def me(current_user: UserDTO = Depends(get_current_user)):
        return {"role": current_user.role}

    client = TestClient(app)
    response = client.get("/me", headers={"Authorization": "Bearer token"})
    assert response.status_code == 401


def test_get_current_user_uses_db_role(monkeypatch):
    async def _fake_get_by_id(self, record_id: int):
        if record_id == 7:
            return _db_user(role="viewer")
        if record_id == 9:
            return _tenant()
        return None

    monkeypatch.setattr("apps.shared.core.auth.jwt.decode", lambda *args, **kwargs: _token_payload(role="viewer"))
    monkeypatch.setattr("apps.shared.core.auth.BaseRepository.get_by_id", _fake_get_by_id)

    app = FastAPI()
    app.dependency_overrides[get_db] = _fake_db

    @app.get("/me")
    async def me(current_user: UserDTO = Depends(get_current_user)):
        return {"role": current_user.role}

    client = TestClient(app)
    response = client.get("/me", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.json()["role"] == "viewer"
