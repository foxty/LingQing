"""Unit tests for skill service and repository."""

from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from apps.shared.core.exceptions import DuplicateResourceError, ResourceNotFoundError, ValidationError
from apps.tenant_app_service.skills.domain import SkillConfigData, SkillType
from apps.tenant_app_service.skills.paths import SkillPaths
from apps.tenant_app_service.skills.repository import (
    SkillConfigStore,
    SkillRepository,
)
from apps.tenant_app_service.skills.resolution import SkillResolver
from apps.tenant_app_service.skills.service import SkillService
from apps.tenant_app_service.skills.validator import SkillZipValidator

# ==============================================================================
# SkillConfigStore tests
# ==============================================================================


class TestSkillConfigStore:
    def test_write_and_read_config(self, tmp_path):
        store = SkillConfigStore(str(tmp_path))
        config = SkillConfigData(name="test-skill", type=SkillType.TENANT, description="A test skill")
        store.write_config(str(tmp_path), config)

        read = store.read_config(str(tmp_path), "test-skill")
        assert read is not None
        assert read.name == "test-skill"
        assert read.description == "A test skill"
        assert read.enabled is True

    def test_read_nonexistent_config_returns_none(self, tmp_path):
        store = SkillConfigStore(str(tmp_path))
        result = store.read_config(str(tmp_path), "nonexistent")
        assert result is None

    def test_env_vars_encrypted_at_rest(self, tmp_path):
        store = SkillConfigStore(str(tmp_path))
        config = SkillConfigData(
            name="secret-skill", type=SkillType.TENANT, description="", env_vars={"API_KEY": "sk-abc123"}
        )
        store.write_config(str(tmp_path), config)

        # Read raw JSON to verify encryption
        config_path = os.path.join(str(tmp_path), "secret-skill.config.json")
        with open(config_path) as f:
            raw = json.load(f)
        assert raw["env_vars"]["API_KEY"].startswith("enc:")

    def test_env_vars_decrypted_on_read(self, tmp_path):
        store = SkillConfigStore(str(tmp_path))
        config = SkillConfigData(
            name="secret-skill", type=SkillType.TENANT, description="", env_vars={"API_KEY": "sk-abc123"}
        )
        store.write_config(str(tmp_path), config)

        read = store.read_config(str(tmp_path), "secret-skill")
        assert read is not None
        assert read.env_vars["API_KEY"] == "sk-abc123"

    def test_update_env_vars_creates_config_if_missing(self, tmp_path):
        store = SkillConfigStore(str(tmp_path))
        result = store.update_env_vars(str(tmp_path), "new-skill", {"KEY": "val"})
        assert result.env_vars["KEY"] == "val"

    def test_update_env_vars_merges_with_existing(self, tmp_path):
        store = SkillConfigStore(str(tmp_path))
        store.update_env_vars(str(tmp_path), "skill-a", {"K1": "v1"})
        store.update_env_vars(str(tmp_path), "skill-a", {"K2": "v2"})
        read = store.read_config(str(tmp_path), "skill-a")
        assert read is not None
        assert read.env_vars == {"K1": "v1", "K2": "v2"}

    def test_get_masked_env_vars(self, tmp_path):
        store = SkillConfigStore(str(tmp_path))
        store.update_env_vars(str(tmp_path), "skill-a", {"API_KEY": "sk-abc123"})
        masked = store.get_masked_env_vars(str(tmp_path), "skill-a")
        assert masked["API_KEY"] != "sk-abc123"
        assert "****" in masked["API_KEY"]

    def test_get_masked_env_vars_empty_when_no_config(self, tmp_path):
        store = SkillConfigStore(str(tmp_path))
        assert store.get_masked_env_vars(str(tmp_path), "no-skill") == {}

    def test_toggle_enabled(self, tmp_path):
        store = SkillConfigStore(str(tmp_path))
        store.update_env_vars(str(tmp_path), "skill-a", {})
        result = store.toggle_enabled(str(tmp_path), "skill-a", False)
        assert result is False
        read = store.read_config(str(tmp_path), "skill-a")
        assert read is not None
        assert read.enabled is False

    def test_toggle_enabled_creates_config_if_missing(self, tmp_path):
        store = SkillConfigStore(str(tmp_path))
        result = store.toggle_enabled(str(tmp_path), "new-skill", True)
        assert result is True


# ==============================================================================
# SkillZipValidator tests
# ==============================================================================


def _create_valid_zip(tmp_path: Path, name: str = "test-skill", extra_file: str | None = None) -> bytes:
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        content = f"---\nname: {name}\ndescription: A test skill\n---\n\nThis is the body."
        zf.writestr(f"{name}/SKILL.md", content)
        if extra_file:
            zf.writestr(f"{name}/{extra_file}", "content")
    return zip_path.read_bytes()


def _invalid_zip_bytes() -> bytes:
    return b"not a zip file"


class TestSkillZipValidator:
    def test_valid_zip_passes(self, tmp_path):
        data = _create_valid_zip(tmp_path)
        validator = SkillZipValidator()
        import io

        result = validator.validate_zip(io.BytesIO(data))
        assert result["name"] == "test-skill"
        assert result["description"] == "A test skill"

    def test_valid_zip_with_name_check(self, tmp_path):
        data = _create_valid_zip(tmp_path, name="matching-name")
        validator = SkillZipValidator()
        import io

        result = validator.validate_zip(io.BytesIO(data), expected_name="matching-name")
        assert result["name"] == "matching-name"

    def test_rejects_name_mismatch(self, tmp_path):
        data = _create_valid_zip(tmp_path, name="name-a")
        validator = SkillZipValidator()
        import io

        with pytest.raises(ValidationError, match="does not match expected name"):
            validator.validate_zip(io.BytesIO(data), expected_name="name-b")

    def test_rejects_missing_skill_md(self, tmp_path):
        zip_path = tmp_path / "bad.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("some-file.txt", "hello")
        validator = SkillZipValidator()
        import io

        with pytest.raises(ValidationError, match="SKILL.md"):
            validator.validate_zip(io.BytesIO(zip_path.read_bytes()))

    def test_rejects_oversized_zip(self, tmp_path):
        data = b"x" * (10 * 1024 * 1024 + 1)
        validator = SkillZipValidator()
        import io

        with pytest.raises(ValidationError, match="10MB"):
            validator.validate_zip(io.BytesIO(data))

    def test_rejects_invalid_zip_format(self, tmp_path):
        validator = SkillZipValidator()
        import io

        with pytest.raises(ValidationError, match="ZIP"):
            validator.validate_zip(io.BytesIO(b"not a zip at all"))

    def test_validate_skill_name_rejects_empty(self):
        validator = SkillZipValidator()
        with pytest.raises(ValidationError):
            validator.validate_skill_name("")

    def test_validate_skill_name_rejects_invalid_chars(self):
        validator = SkillZipValidator()
        with pytest.raises(ValidationError):
            validator.validate_skill_name("with spaces")

    def test_validate_skill_name_accepts_valid(self):
        validator = SkillZipValidator()
        result = validator.validate_skill_name("my-skill-123")
        assert result == "my-skill-123"


# ==============================================================================
# SkillRepository tests
# ==============================================================================


class TestSkillRepository:
    def test_list_builtin_skills(self, tmp_path):
        builtin_dir = tmp_path / "skills"
        builtin_dir.mkdir(parents=True)
        # Create a standard skill dir with SKILL.md
        skill_dir = builtin_dir / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: Builtin skill\n---\n\nBody")
        from apps.tenant_app_service.skills.paths import SkillPaths
        paths = SkillPaths(data_root=str(tmp_path))
        fs = SkillRepository(str(tmp_path), paths=paths)
        skills = fs.list_builtin_skills()
        assert len(skills) == 1
        assert skills[0]["name"] == "test-skill"

    def test_list_builtin_skills_returns_empty_when_no_dir(self, tmp_path):
        from apps.tenant_app_service.skills.paths import SkillPaths
        paths = SkillPaths(data_root=str(tmp_path))
        fs = SkillRepository(str(tmp_path), paths=paths)
        assert fs.list_builtin_skills() == []

    def test_missing_dir_is_cached_and_reloads_when_created(self, tmp_path, caplog):
        repo = SkillRepository(str(tmp_path))
        missing = str(tmp_path / "tenants" / "tenant_2" / "skills")

        with caplog.at_level("WARNING"):
            assert repo.load_skill_configs(missing, SkillType.TENANT) == {}
            assert repo.load_skill_configs(missing, SkillType.TENANT) == {}
        assert not [r for r in caplog.records if "Skill directory not found" in r.getMessage()]

        skill_dir = Path(missing) / "later-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: later-skill\ndescription: Added later\n---\n\nBody")

        loaded = repo.load_skill_configs(missing, SkillType.TENANT)
        assert "later-skill" in loaded

    def test_load_skill_with_string_allowed_tools(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "ops-comma"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: ops-comma\ndescription: Comma-separated tools.\n"
            "allowed-tools: search_data_assets, search_documents\n---\n\nBody\n",
            encoding="utf-8",
        )
        repo = SkillRepository(str(tmp_path))
        loaded = repo.load_skill_configs(str(skills_dir), SkillType.TENANT)
        assert "ops-comma" in loaded
        assert [t.name for t in loaded["ops-comma"].tools] == ["search_data_assets", "search_documents"]

    def test_load_skill_with_colons_in_tool_names(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skill_dir = skills_dir / "agent-browser"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: agent-browser\ndescription: Browser automation.\n"
            "allowed-tools: Bash(agent-browser:*), Bash(npx agent-browser:*)\n---\n\nBody\n",
            encoding="utf-8",
        )
        repo = SkillRepository(str(tmp_path))
        loaded = repo.load_skill_configs(str(skills_dir), SkillType.TENANT)
        assert "agent-browser" in loaded
        assert [t.name for t in loaded["agent-browser"].tools] == [
            "Bash(agent-browser:*)",
            "Bash(npx agent-browser:*)",
        ]


# ==============================================================================
# SkillService tests
# ==============================================================================


class TestSkillService:
    def test_list_skills_empty(self, tmp_path):
        # Create empty skills dir to override default builtin location
        (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
        svc = SkillService(
            data_root=str(tmp_path),
            resolver=SkillResolver(data_root=str(tmp_path), tool_registry={}),
        )
        skills = svc.list_skills(tenant_id=1, user_id=1)
        assert skills == []

    def test_get_skill_not_found(self, tmp_path):
        # Create empty skills dir to override default builtin location
        (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
        svc = SkillService(
            data_root=str(tmp_path),
            resolver=SkillResolver(data_root=str(tmp_path), tool_registry={}),
        )
        result = svc.get_skill(tenant_id=1, user_id=1, name="nonexistent")
        assert result is None

    def test_toggle_enabled_creates_config(self, tmp_path):
        # Create empty skills dir to override default builtin location
        (tmp_path / "skills").mkdir(parents=True, exist_ok=True)
        svc = SkillService(
            data_root=str(tmp_path),
            resolver=SkillResolver(data_root=str(tmp_path), tool_registry={}),
        )
        skills_dir = tmp_path / "tenants" / "tenant_1" / "skills" / "test-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("---\nname: test-skill\ndescription: Test\n---\n\nBody")
        result = svc.toggle_enabled(
            tenant_id=1, user_id=1, scope=SkillType.TENANT, skill_name="test-skill", enabled=False
        )
        assert result.enabled is False


# ==============================================================================
# Integration-style: Full upload path through service + filesystem
# ==============================================================================


def _make_skill_zip(tmp_path: Path, name: str, extra_file: str | None = None) -> bytes:
    """Create a valid skill ZIP in memory (flat structure, no dir prefix)."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        content = f"---\nname: {name}\ndescription: {name} desc\n---\n\nBody"
        zf.writestr("SKILL.md", content)
        if extra_file:
            zf.writestr(extra_file, "content")
    return buf.getvalue()


class TestSkillImportFromUrl:
    def test_import_delegates_to_create_skill(self, tmp_path):
        svc = SkillService(data_root=str(tmp_path))
        svc._repo._paths = SkillPaths(data_root=str(tmp_path))
        zip_data = _make_skill_zip(tmp_path, "imported-skill")
        import io

        mock_fetcher = MagicMock()
        mock_fetcher.fetch_as_zip.return_value = io.BytesIO(zip_data)
        svc._package_fetcher = mock_fetcher

        result = svc.import_skill_from_url(
            tenant_id=1,
            user_id=1,
            skill_type=SkillType.TENANT,
            url="anthropics/skills/imported-skill",
            created_by="user1",
        )

        assert result.name == "imported-skill"
        mock_fetcher.fetch_as_zip.assert_called_once()
        skill_dir = tmp_path / "tenants" / "tenant_1" / "skills" / "imported-skill"
        assert (skill_dir / "SKILL.md").exists()


class TestSkillUploadIntegration:
    """Integration tests for the full upload flow through SkillService."""

    def test_upload_tenant_skill_happy_path(self, tmp_path):
        svc = SkillService(data_root=str(tmp_path))
        svc._repo._paths = SkillPaths(data_root=str(tmp_path))
        zip_data = _make_skill_zip(tmp_path, "my-skill")
        import io

        result = svc.create_skill(
            tenant_id=1,
            user_id=1,
            skill_type=SkillType.TENANT,
            zip_file=io.BytesIO(zip_data),
            created_by="user1",
        )
        assert result.name == "my-skill"
        assert result.type == SkillType.TENANT
        assert result.enabled is True
        # Verify files written to disk
        skill_dir = tmp_path / "tenants" / "tenant_1" / "skills" / "my-skill"
        assert (skill_dir / "SKILL.md").exists()

    def test_upload_personal_skill_happy_path(self, tmp_path):
        svc = SkillService(data_root=str(tmp_path))
        svc._repo._paths = SkillPaths(data_root=str(tmp_path))
        zip_data = _make_skill_zip(tmp_path, "my-personal-skill")
        import io

        result = svc.create_skill(
            tenant_id=1,
            user_id=42,
            skill_type=SkillType.PERSONAL,
            zip_file=io.BytesIO(zip_data),
            created_by="user42",
        )
        assert result.name == "my-personal-skill"
        assert result.type == SkillType.PERSONAL

    def test_upload_duplicate_name_raises(self, tmp_path):
        svc = SkillService(data_root=str(tmp_path))
        svc._repo._paths = SkillPaths(data_root=str(tmp_path))
        zip_data = _make_skill_zip(tmp_path, "dup-skill")
        import io

        svc.create_skill(
            tenant_id=1, user_id=1, skill_type=SkillType.TENANT, zip_file=io.BytesIO(zip_data), created_by="u1"
        )
        with pytest.raises(DuplicateResourceError):
            svc.create_skill(
                tenant_id=1, user_id=1, skill_type=SkillType.TENANT, zip_file=io.BytesIO(zip_data), created_by="u1"
            )

    def test_upload_name_conflict_with_builtin(self, tmp_path):
        # Builtin skills live in <data_root>/skills (per SkillPaths.builtin_dir)
        builtin_dir = tmp_path / "skills"
        builtin_dir.mkdir()
        skill_dir = builtin_dir / "existing-builtin"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: existing-builtin\ndescription: Builtin\n---\n\nBody")
        svc = SkillService(data_root=str(tmp_path))
        zip_data = _make_skill_zip(tmp_path, "existing-builtin")
        import io

        with pytest.raises(DuplicateResourceError, match="conflicts"):
            svc.create_skill(
                tenant_id=1, user_id=1, skill_type=SkillType.TENANT, zip_file=io.BytesIO(zip_data), created_by="u1"
            )

    def test_upload_orphaned_skill_dir_raises_validation_error(self, tmp_path):
        svc = SkillService(data_root=str(tmp_path))
        svc._repo._paths = SkillPaths(data_root=str(tmp_path))
        skill_dir = tmp_path / "tenants" / "tenant_1" / "skills" / "broken-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: broken-skill\ndescription:\n---\n\nBody\n",
            encoding="utf-8",
        )
        zip_data = _make_skill_zip(tmp_path, "broken-skill")
        import io

        with pytest.raises(ValidationError, match="could not be loaded"):
            svc.create_skill(
                tenant_id=1, user_id=1, skill_type=SkillType.TENANT, zip_file=io.BytesIO(zip_data), created_by="u1"
            )

    def test_upload_invalid_type_raises(self, tmp_path):
        svc = SkillService(data_root=str(tmp_path))
        svc._repo._paths = SkillPaths(data_root=str(tmp_path))
        import io

        with pytest.raises(ValidationError, match="Invalid skill type"):
            svc.create_skill(
                tenant_id=1, user_id=1, skill_type=SkillType.BUILTIN, zip_file=io.BytesIO(b"ignored"), created_by="u1"
            )

    def test_upload_oversized_zip_raises(self, tmp_path):
        svc = SkillService(data_root=str(tmp_path))
        svc._repo._paths = SkillPaths(data_root=str(tmp_path))
        import io

        with pytest.raises(ValidationError, match="10MB"):
            svc.create_skill(
                tenant_id=1,
                user_id=1,
                skill_type=SkillType.TENANT,
                zip_file=io.BytesIO(b"x" * (10 * 1024 * 1024 + 1)),
                created_by="u1",
            )

    def test_delete_tenant_skill(self, tmp_path):
        svc = SkillService(data_root=str(tmp_path))
        svc._repo._paths = SkillPaths(data_root=str(tmp_path))
        zip_data = _make_skill_zip(tmp_path, "to-delete")
        import io

        svc.create_skill(
            tenant_id=1, user_id=1, skill_type=SkillType.TENANT, zip_file=io.BytesIO(zip_data), created_by="u1"
        )
        svc.delete_skill(tenant_id=1, user_id=1, skill_type=SkillType.TENANT, name="to-delete")
        skill_dir = tmp_path / "tenants" / "tenant_1" / "skills" / "to-delete"
        assert not skill_dir.exists()

    def test_env_vars_full_lifecycle(self, tmp_path):
        svc = SkillService(data_root=str(tmp_path))
        svc._repo._paths = SkillPaths(data_root=str(tmp_path))
        zip_data = _make_skill_zip(tmp_path, "env-skill")
        import io

        svc.create_skill(tenant_id=1, user_id=1, skill_type="tenant", zip_file=io.BytesIO(zip_data), created_by="u1")
        # Update env vars
        masked = svc.update_env_vars(
            tenant_id=1, user_id=1, scope="tenant", skill_name="env-skill", env_vars={"KEY": "secret-val"}
        )
        assert "****" in masked["KEY"]
        # Read back (masked)
        read = svc.get_env_vars(tenant_id=1, user_id=1, scope="tenant", skill_name="env-skill")
        assert "****" in read["KEY"]


# ==============================================================================
# ZIP prefix stripping tests
# ==============================================================================


def _make_zip_with(members: list[tuple[str, str]]) -> bytes:
    """Helper: create ZIP bytes from (path, content) pairs."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for path, content in members:
            zf.writestr(path, content)
    buf.seek(0)
    return buf.read()


# ==============================================================================
# SkillConfigData tests
# ==============================================================================


class TestSkillConfigData:
    def test_to_json_roundtrip(self):
        config = SkillConfigData(name="test", type=SkillType.TENANT, description="desc", enabled=True)
        raw = config.to_json()
        parsed = SkillConfigData.from_json(raw)
        assert parsed.name == "test"
        assert parsed.type == SkillType.TENANT
        assert parsed.enabled is True

    def test_from_json_missing_fields_default(self):
        raw = json.dumps({"name": "test"})
        parsed = SkillConfigData.from_json(raw)
        assert parsed.name == "test"
        assert parsed.type == SkillType.TENANT
        assert parsed.enabled is True
        assert parsed.env_vars == {}

    def test_from_json_backward_compat_empty_type(self):
        """Old config files may have empty type string, should default to tenant."""
        raw = json.dumps({"name": "old-skill", "type": "", "description": "legacy"})
        parsed = SkillConfigData.from_json(raw)
        assert parsed.name == "old-skill"
        assert parsed.type == SkillType.TENANT
        assert parsed.description == "legacy"
        assert parsed.description == "legacy"
