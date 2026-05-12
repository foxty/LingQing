"""Unit tests for skills router."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.shared.core.auth import get_current_user
from apps.shared.core.exception_handlers import register_exception_handlers
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.routers import skills
from apps.tenant_app_service.skills.dtos import SkillInfo


@pytest.fixture
def app():
    api = FastAPI()
    register_exception_handlers(api)
    api.include_router(skills.router)

    async def _fake_user():
        return UserDTO(id=1, username="admin", role="admin", tenant_id=1, tenant_name="t1")

    async def _fake_db():
        yield object()

    api.dependency_overrides[get_current_user] = _fake_user
    api.dependency_overrides[get_db] = _fake_db
    return api


@pytest.fixture
def client(app):
    return TestClient(app)


class TestListSkills:
    def test_list_all_skills(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=_ALL_SKILLS)
        resp = client.get("/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3

    def test_filter_builtin(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=_ALL_SKILLS)
        resp = client.get("/skills?type=builtin")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["type"] == "builtin"

    def test_filter_tenant(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=_ALL_SKILLS)
        resp = client.get("/skills?type=tenant")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_filter_personal(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=_ALL_SKILLS)
        resp = client.get("/skills?type=personal")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_empty_skills(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=[])
        resp = client.get("/skills")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []


class TestGetSkill:
    def test_get_builtin_skill(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=_ALL_SKILLS)
        resp = client.get("/skills/data-analyst")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "data-analyst"
        assert data["type"] == "builtin"

    def test_get_tenant_skill(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=_ALL_SKILLS)
        resp = client.get("/skills/my-tenant-skill")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "my-tenant-skill"
        assert data["type"] == "tenant"

    def test_get_not_found(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=[])
        resp = client.get("/skills/nonexistent")
        assert resp.status_code == 404


class TestImportSkill:
    def test_import_tenant_skill_success(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=[])
        resp = client.post(
            "/skills/import?type=tenant",
            json={"url": "https://skills.sh/owner/repo/test-skill"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "new-skill"

    def test_import_skill_validation_error(self, app, client):
        svc = _FakeSkillService(skills=[])
        svc._raise_on_import = True
        app.dependency_overrides[skills._get_skill_service] = lambda: svc
        resp = client.post(
            "/skills/import?type=tenant",
            json={"url": "https://evil.com/bad"},
        )
        assert resp.status_code == 400


class TestCreateSkill:
    def test_create_tenant_skill_success(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=[])
        resp = client.post("/skills?type=tenant", files={"file": ("test.zip", b"fake-zip-content", "application/zip")})
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "new-skill"

    def test_create_skill_wrong_file_type(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=[])
        resp = client.post("/skills?type=tenant", files={"file": ("test.txt", b"hello", "text/plain")})
        assert resp.status_code == 400
        assert "ZIP" in resp.text

    def test_create_skill_validation_error(self, app, client):
        svc = _FakeSkillService(skills=[])
        svc._raise_on_create = True
        app.dependency_overrides[skills._get_skill_service] = lambda: svc
        resp = client.post("/skills?type=tenant", files={"file": ("test.zip", b"fake-zip-content", "application/zip")})
        assert resp.status_code == 400


class TestDeleteSkill:
    def test_delete_tenant_skill_success(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=_ALL_SKILLS)
        resp = client.delete("/skills/my-tenant-skill?type=tenant")
        assert resp.status_code == 204

    def test_delete_not_found(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=[])
        resp = client.delete("/skills/nonexistent?type=tenant")
        assert resp.status_code == 404


class TestEnvVars:
    def test_get_env_vars(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=_ALL_SKILLS)
        resp = client.get("/skills/tenant/my-tenant-skill/env-vars")
        assert resp.status_code == 200
        data = resp.json()
        assert "env_vars" in data

    def test_update_env_vars(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=_ALL_SKILLS)
        resp = client.put("/skills/tenant/my-tenant-skill/env-vars", json={"env_vars": {"KEY": "val"}})
        assert resp.status_code == 200
        data = resp.json()
        assert "env_vars" in data

    def test_toggle_enabled(self, app, client):
        app.dependency_overrides[skills._get_skill_service] = lambda: _FakeSkillService(skills=_ALL_SKILLS)
        resp = client.patch("/skills/tenant/my-tenant-skill/enabled", json={"enabled": False})
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is False


# --- Fixtures ---

_ALL_SKILLS = [
    SkillInfo(name="data-analyst", type="builtin", description="Data analysis skill"),
    SkillInfo(name="my-tenant-skill", type="tenant", description="Tenant skill", env_var_keys=["API_KEY"]),
    SkillInfo(name="my-personal-skill", type="personal", description="Personal skill"),
]


class _FakeSkillService:
    def __init__(self, skills: list[SkillInfo]):
        self._skills = {s.name: s for s in skills}
        self._raise_on_create = False
        self._raise_on_import = False

    def list_skills(self, tenant_id, user_id, type_filter=None):
        if type_filter:
            return [s for s in self._skills.values() if s.type == type_filter.value]
        return list(self._skills.values())

    def get_skill(self, tenant_id, user_id, name):
        return self._skills.get(name)

    def create_skill(self, tenant_id, user_id, skill_type, zip_file, created_by):
        if self._raise_on_create:
            from apps.shared.core.exceptions import ValidationError

            raise ValidationError("Invalid skill")
        return SkillInfo(name="new-skill", type=skill_type.value, description="Created")

    def import_skill_from_url(self, tenant_id, user_id, skill_type, url, created_by):
        if self._raise_on_import:
            from apps.shared.core.exceptions import ValidationError

            raise ValidationError("Invalid URL")
        return SkillInfo(name="new-skill", type=skill_type.value, description="Imported")

    def delete_skill(self, tenant_id, user_id, skill_type, name):
        if name not in self._skills:
            from apps.shared.core.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError(f"Skill '{name}' not found")

    def get_env_vars(self, tenant_id, user_id, scope, skill_name):
        return {"MASKED_KEY": "****"}

    def update_env_vars(self, tenant_id, user_id, scope, skill_name, env_vars):
        return {"MASKED_KEY": "****"}

    def toggle_enabled(self, tenant_id, user_id, scope, skill_name, enabled):
        return SkillInfo(name=skill_name, type=scope.value, description="", enabled=enabled)
