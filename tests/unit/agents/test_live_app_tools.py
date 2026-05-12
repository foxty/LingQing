"""Unit tests for live app agent tools."""

import json
from types import SimpleNamespace

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.live_app.schemas import LiveAppDeploymentStateDTO, LiveAppListDTO, LiveAppRecordDTO
from apps.tenant_app_service.agents.tools import live_app as live_app_tool
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


class _FakeSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _make_live_app_record(app_id: int = 1) -> LiveAppRecordDTO:
    return LiveAppRecordDTO(
        app_id=app_id,
        name=f"app_{app_id}",
        description=None,
        entry_file="entry.html",
        sdk_version="1.0",
        status="draft",
        data_source_id=10,
        owner_name=None,
        deployment_state=LiveAppDeploymentStateDTO(),
    )


@pytest.fixture(autouse=True)
def _stub_actor_access_checks(monkeypatch):
    async def _fake_get_app_for_actor(self, app_id: int, **kwargs):
        return _make_live_app_record(app_id=app_id)

    async def _fake_require_read_access(self, app_id: int, **kwargs):
        return None

    async def _fake_require_write_access(self, app_id: int, **kwargs):
        return None

    monkeypatch.setattr(live_app_tool.LiveAppService, "get_app_for_actor", _fake_get_app_for_actor, raising=False)
    monkeypatch.setattr(live_app_tool.LiveAppService, "require_read_access", _fake_require_read_access, raising=False)
    monkeypatch.setattr(live_app_tool.LiveAppService, "require_write_access", _fake_require_write_access, raising=False)


@pytest.mark.asyncio
async def test_load_sdk_api_spec_via_read_skill_file(runnable_config):
    """Test that SDK API spec can be loaded via read_skill_file."""
    from apps.tenant_app_service.agents.tools.skill_reference import read_skill_file

    result = await read_skill_file.ainvoke(
        {
            "skill_name": "app-builder",
            "relative_path": "references/javascript_sdk_reference.md",
        },
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.SUCCESS
    content = result.content if isinstance(result.content, str) else result.content.get("content", "")
    assert "LiveAppClient" in content or "declare" in content
    assert "lq-data-table" in content or "LQColumnDef" in content


@pytest.mark.asyncio
async def test_load_python_sdk_spec_via_read_skill_file(runnable_config):
    """Test that Python SDK reference can be loaded via read_skill_file."""
    from apps.tenant_app_service.agents.tools.skill_reference import read_skill_file

    result = await read_skill_file.ainvoke(
        {
            "skill_name": "app-builder",
            "relative_path": "references/python_sdk_reference.md",
        },
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.SUCCESS
    content = result.content if isinstance(result.content, str) else result.content.get("content", "")
    assert "LiveAppClient" in content
    assert "from_environment" in content


@pytest.mark.asyncio
async def test_create_live_app_tool_returns_payload(monkeypatch, runnable_config):
    async def _fake_create_with_artifact(
        self,
        *,
        name: str,
        description: str | None = None,
        owner_id: int | None = None,
        data_source_id: int | None = None,
        thread_id: str | None = None,
    ):
        assert name == "sales_app"
        assert description == "tenant sales app"
        assert owner_id == 123
        assert data_source_id == 88
        assert thread_id == "thread_test_123"
        return SimpleNamespace(
            app=LiveAppRecordDTO(
                app_id=6,
                name=name,
                description=description,
                entry_file="entry.html",
                sdk_version="1.0",
                status="draft",
                data_source_id=data_source_id,
                owner_name=None,
                deployment_state=LiveAppDeploymentStateDTO(),
            ),
            artifact=SimpleNamespace(
                model_dump=lambda: {
                    "type": "artifact",
                    "artifact_type": "app",
                    "id": 101,
                    "url": "/api/apps/6/dev/embed",
                    "title": "sales_app",
                    "metadata": {"app_id": 6},
                }
            ),
        )

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "create_app_with_artifact", _fake_create_with_artifact)

    result = await live_app_tool.create_live_app.ainvoke(
        {"name": "sales_app", "description": "tenant sales app", "data_source_id": 88},
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["app_id"] == 6
    assert payload["name"] == "sales_app"
    assert payload["preview_url"] == "/api/apps/6/dev/embed"
    assert payload["artifact"]["artifact_type"] == "app"
    assert payload["artifact"]["url"] == "/api/apps/6/dev/embed"


@pytest.mark.asyncio
async def test_create_live_app_tool_maps_validation_error(monkeypatch, runnable_config):
    async def _fake_create_with_artifact(
        self,
        *,
        name: str,
        description: str | None = None,
        owner_id: int | None = None,
        data_source_id: int | None = None,
        thread_id: str | None = None,
    ):
        raise ValidationError("name required", details={"code": "APP_INVALID_NAME"})

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "create_app_with_artifact", _fake_create_with_artifact)

    result = await live_app_tool.create_live_app.ainvoke({"name": ""}, config=runnable_config)
    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code == "APP_INVALID_NAME"


@pytest.mark.asyncio
async def test_list_live_apps_tool_returns_payload(monkeypatch, runnable_config):
    async def _fake_list_apps_for_actor(self, *, actor):
        return LiveAppListDTO(
            apps=[
                LiveAppRecordDTO(
                    app_id=1,
                    name="sales_app",
                    description=None,
                    entry_file="entry.html",
                    sdk_version="1.0",
                    status="draft",
                    data_source_id=10,
                    owner_name=None,
                    deployment_state=LiveAppDeploymentStateDTO(),
                ),
                LiveAppRecordDTO(
                    app_id=2,
                    name="ops_app",
                    description=None,
                    entry_file="entry.html",
                    sdk_version="1.0",
                    status="draft",
                    data_source_id=11,
                    owner_name=None,
                    deployment_state=LiveAppDeploymentStateDTO(),
                ),
            ],
            count=2,
        )

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_apps_for_actor", _fake_list_apps_for_actor)

    result = await live_app_tool.list_live_apps.ainvoke({}, config=runnable_config)
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["count"] == 2
    assert payload["apps"][0]["name"] == "sales_app"
    assert payload["apps"][0]["preview_url"] == "/api/apps/1/dev/embed"


@pytest.mark.asyncio
async def test_get_live_app_tool_maps_not_found(monkeypatch, runnable_config):
    from apps.shared.core.exceptions import ResourceNotFoundError

    async def _fake_get_app_for_actor(self, app_id: int, **kwargs):
        raise ResourceNotFoundError("Live app not found", details={"code": "APP_NOT_FOUND", "app_id": app_id})

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "get_app_for_actor", _fake_get_app_for_actor)

    result = await live_app_tool.get_live_app.ainvoke({"app_id": 999}, config=runnable_config)
    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code == "LIVE_APP_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_live_app_tool_returns_preview_url(monkeypatch, runnable_config):
    async def _fake_get_app(self, app_id: int):
        assert app_id == 31
        return LiveAppRecordDTO(
            app_id=31,
            name="sales_app",
            description=None,
            entry_file="entry.html",
            sdk_version="1.0",
            status="draft",
            data_source_id=10,
            owner_name=None,
            deployment_state=LiveAppDeploymentStateDTO(),
        )

    async def _fake_list_files(self, app_id: int, **kwargs):
        return {"files": ["entry.html"]}

    async def _fake_list_migrations(self, app_id: int, **kwargs):
        return {"migrations": []}

    async def _fake_list_commits(self, app_id: int, **kwargs):
        return {"commits": []}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "get_app", _fake_get_app)
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_files", _fake_list_files)
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_migrations", _fake_list_migrations)
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_commits", _fake_list_commits)

    result = await live_app_tool.get_live_app.ainvoke({"app_id": 31}, config=runnable_config)
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["app_id"] == 31
    assert payload["preview_url"] == "/api/apps/31/dev/embed"


@pytest.mark.asyncio
async def test_get_live_app_tool_returns_dev_context(monkeypatch, runnable_config):
    async def _fake_get_app(self, app_id: int):
        return LiveAppRecordDTO(
            app_id=31,
            name="sales_app",
            description=None,
            entry_file="entry.html",
            sdk_version="1.0",
            status="draft",
            data_source_id=10,
            owner_name=None,
            deployment_state=LiveAppDeploymentStateDTO(),
        )

    async def _fake_list_files(self, app_id: int, **kwargs):
        return {"files": ["entry.html", "src/app.js", "migrations/001_init.up.sql"]}

    async def _fake_list_migrations(self, app_id: int, **kwargs):
        return {"migrations": [{"name": "001_init", "applied": True, "has_down": True}]}

    async def _fake_list_commits(self, app_id: int, **kwargs):
        return {"commits": [{"hash": "abc123", "message": "Initial commit"}]}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "get_app", _fake_get_app)
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_files", _fake_list_files)
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_migrations", _fake_list_migrations)
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_commits", _fake_list_commits)

    result = await live_app_tool.get_live_app.ainvoke({"app_id": 31}, config=runnable_config)
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    ctx = payload["dev_context"]
    assert ctx["files"] == ["entry.html", "src/app.js", "migrations/001_init.up.sql"]
    assert ctx["migrations"][0]["name"] == "001_init"
    assert ctx["migrations"][0]["applied"] is True
    assert ctx["recent_commits"][0]["hash"] == "abc123"


@pytest.mark.asyncio
async def test_get_live_app_tool_dev_context_graceful_on_failure(monkeypatch, runnable_config):
    """Dev context fields should be None when subsidiary calls fail, not crash the tool."""

    async def _fake_get_app(self, app_id: int):
        return LiveAppRecordDTO(
            app_id=31,
            name="sales_app",
            description=None,
            entry_file="entry.html",
            sdk_version="1.0",
            status="draft",
            data_source_id=10,
            owner_name=None,
            deployment_state=LiveAppDeploymentStateDTO(),
        )

    async def _fake_list_files_error(self, app_id: int, **kwargs):
        raise RuntimeError("disk error")

    async def _fake_list_migrations_error(self, app_id: int, **kwargs):
        raise RuntimeError("db error")

    async def _fake_list_commits_error(self, app_id: int, **kwargs):
        raise RuntimeError("no git repo")

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "get_app", _fake_get_app)
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_files", _fake_list_files_error)
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_migrations", _fake_list_migrations_error)
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_commits", _fake_list_commits_error)

    result = await live_app_tool.get_live_app.ainvoke({"app_id": 31}, config=runnable_config)
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["app_id"] == 31
    ctx = payload["dev_context"]
    assert ctx["files"] is None
    assert ctx["migrations"] is None
    assert ctx["recent_commits"] is None


@pytest.mark.asyncio
async def test_diff_app_environments_tool_returns_payload(monkeypatch, runnable_config):
    async def _fake_diff_environments(self, app_id: int, *, from_environment: str, to_environment: str):
        assert app_id == 31
        assert from_environment == "dev"
        assert to_environment == "prod"
        return {
            "app_id": 31,
            "from_environment": "dev",
            "to_environment": "prod",
            "files": {"only_in_from": [], "only_in_to": [], "changed": [{"path": "entry.html"}]},
            "summary": {"in_sync": False, "changed_count": 1},
        }

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "diff_environments", _fake_diff_environments)

    result = await live_app_tool.diff_app_environments.ainvoke(
        {"app_id": 31, "from_environment": "dev", "to_environment": "prod"},
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["summary"]["in_sync"] is False
    assert payload["summary"]["changed_count"] == 1


@pytest.mark.asyncio
async def test_list_app_files_tool_returns_payload(monkeypatch, runnable_config):
    async def _fake_list_files(self, app_id: int, **kwargs):
        assert app_id == 9
        return {"app_id": 9, "files": ["entry.html", "src/main.js"]}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_files", _fake_list_files)

    result = await live_app_tool.list_app_files.ainvoke({"app_id": 9}, config=runnable_config)
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["files"] == ["entry.html", "src/main.js"]


@pytest.mark.asyncio
async def test_grep_app_files_tool_returns_payload(monkeypatch, runnable_config):
    async def _fake_grep_files_for_actor(self, *, app_id, actor, pattern, **kwargs):
        assert app_id == 9
        assert pattern == "foo"
        return {
            "app_id": 9,
            "environment": "dev",
            "pattern": "foo",
            "matches": [{"path": "src/a.js", "line": 2, "text": "foo bar"}],
            "truncated": False,
        }

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "grep_files_for_actor", _fake_grep_files_for_actor)

    result = await live_app_tool.grep_app_files.ainvoke({"app_id": 9, "pattern": "foo"}, config=runnable_config)
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["matches"][0]["path"] == "src/a.js"


@pytest.mark.asyncio
async def test_read_app_file_tool_returns_payload(monkeypatch, runnable_config):
    async def _fake_read_file_for_actor(self, app_id: int, path: str, **kwargs):
        assert app_id == 10
        assert path == "src/main.js"
        return {"app_id": 10, "path": path, "content": "console.log(1)"}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "read_file_for_actor", _fake_read_file_for_actor)

    result = await live_app_tool.read_app_file.ainvoke({"app_id": 10, "path": "src/main.js"}, config=runnable_config)
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["content"] == "console.log(1)"


@pytest.mark.asyncio
async def test_read_app_file_tool_with_line_range(monkeypatch, runnable_config):
    """Verify start_line/end_line slicing returns correct subset of lines."""
    file_content = "line1\nline2\nline3\nline4\nline5"

    async def _fake_read(self, app_id: int, path: str, **kwargs):
        return {"app_id": 10, "path": path, "content": file_content}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "read_file_for_actor", _fake_read)

    result = await live_app_tool.read_app_file.ainvoke(
        {"app_id": 10, "path": "src/main.js", "start_line": 2, "end_line": 4},
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["content"] == "line2\nline3\nline4"
    assert payload["total_lines"] == 5
    assert payload["start_line"] == 2
    assert payload["end_line"] == 4


@pytest.mark.asyncio
async def test_read_app_file_tool_start_line_only(monkeypatch, runnable_config):
    """start_line without end_line should read from start_line to end of file."""
    file_content = "a\nb\nc\nd\ne"

    async def _fake_read(self, app_id: int, path: str, **kwargs):
        return {"app_id": 10, "path": path, "content": file_content}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "read_file_for_actor", _fake_read)

    result = await live_app_tool.read_app_file.ainvoke(
        {"app_id": 10, "path": "src/main.js", "start_line": 3},
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["content"] == "c\nd\ne"


@pytest.mark.asyncio
async def test_read_app_file_tool_line_out_of_range(monkeypatch, runnable_config):
    """start_line beyond file length should return an error."""

    async def _fake_read(self, app_id: int, path: str, **kwargs):
        return {"app_id": 10, "path": path, "content": "only\ntwo\nlines"}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "read_file_for_actor", _fake_read)

    result = await live_app_tool.read_app_file.ainvoke(
        {"app_id": 10, "path": "src/main.js", "start_line": 100},
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "LIVE_APP_FILE_LINE_OUT_OF_RANGE"


@pytest.mark.asyncio
async def test_read_app_file_tool_invalid_line_range(monkeypatch, runnable_config):
    """start_line > end_line should return an error."""

    async def _fake_read(self, app_id: int, path: str, **kwargs):
        return {"app_id": 10, "path": path, "content": "a\nb\nc"}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "read_file_for_actor", _fake_read)

    result = await live_app_tool.read_app_file.ainvoke(
        {"app_id": 10, "path": "src/main.js", "start_line": 3, "end_line": 1},
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "LIVE_APP_FILE_INVALID_LINE_RANGE"


@pytest.mark.asyncio
async def test_read_app_file_tool_no_range_returns_full(monkeypatch, runnable_config):
    """Omitting start_line/end_line should return the full file (backward compat)."""

    async def _fake_read(self, app_id: int, path: str, **kwargs):
        return {"app_id": 10, "path": path, "content": "full\nfile\ncontent"}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "read_file_for_actor", _fake_read)

    result = await live_app_tool.read_app_file.ainvoke(
        {"app_id": 10, "path": "src/main.js"},
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["content"] == "full\nfile\ncontent"
    # No range metadata when no range requested
    assert "total_lines" not in payload


@pytest.mark.asyncio
async def test_patch_app_file_tool_success(monkeypatch, runnable_config):
    """patch_app_file should read, find unique match, replace, and write back."""
    current_content = "function hello() {\n  return 'world';\n}\n"

    async def _fake_read(self, app_id: int, path: str, **kwargs):
        return {"app_id": 10, "path": path, "content": current_content}

    write_calls = []

    async def _fake_write(self, *, app_id, path, content, actor, environment="dev"):
        write_calls.append(content)
        return {"app_id": app_id, "path": path, "updated": True, "committed": True}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "read_file_for_actor", _fake_read)
    monkeypatch.setattr(live_app_tool.LiveAppService, "write_file_for_actor", _fake_write)

    result = await live_app_tool.patch_app_file.ainvoke(
        {
            "app_id": 10,
            "path": "src/main.js",
            "old_text": "return 'world';",
            "new_text": "return 'patched';",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["patch_applied"] is True
    assert len(write_calls) == 1
    assert "return 'patched';" in write_calls[0]
    assert "return 'world';" not in write_calls[0]


@pytest.mark.asyncio
async def test_patch_app_file_tool_text_not_found(monkeypatch, runnable_config):
    """patch_app_file should error when old_text is not in the file."""

    async def _fake_read(self, app_id: int, path: str, **kwargs):
        return {"app_id": 10, "path": path, "content": "hello world"}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "read_file_for_actor", _fake_read)

    result = await live_app_tool.patch_app_file.ainvoke(
        {
            "app_id": 10,
            "path": "src/main.js",
            "old_text": "nonexistent text",
            "new_text": "replacement",
        },
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "LIVE_APP_PATCH_TEXT_NOT_FOUND"


@pytest.mark.asyncio
async def test_patch_app_file_tool_ambiguous_match(monkeypatch, runnable_config):
    """patch_app_file should error when old_text matches more than once."""

    async def _fake_read(self, app_id: int, path: str, **kwargs):
        return {"app_id": 10, "path": path, "content": "foo bar foo bar foo"}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "read_file_for_actor", _fake_read)

    result = await live_app_tool.patch_app_file.ainvoke(
        {
            "app_id": 10,
            "path": "src/main.js",
            "old_text": "foo",
            "new_text": "baz",
        },
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "LIVE_APP_PATCH_TEXT_AMBIGUOUS"


@pytest.mark.asyncio
async def test_patch_app_file_tool_validation_error(monkeypatch, runnable_config):
    """patch_app_file should propagate ValidationError from write."""

    async def _fake_read(self, app_id: int, path: str, **kwargs):
        return {"app_id": 10, "path": path, "content": "hello world"}

    async def _fake_write(self, *, app_id, path, content, actor, environment="dev"):
        raise ValidationError("invalid path", details={"code": "APP_INVALID_FILE_PATH"})

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "read_file_for_actor", _fake_read)
    monkeypatch.setattr(live_app_tool.LiveAppService, "write_file_for_actor", _fake_write)

    result = await live_app_tool.patch_app_file.ainvoke(
        {
            "app_id": 10,
            "path": "src/main.js",
            "old_text": "hello",
            "new_text": "goodbye",
        },
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "APP_INVALID_FILE_PATH"


@pytest.mark.asyncio
async def test_write_app_file_tool_maps_validation_error(monkeypatch, runnable_config):
    from apps.shared.core.exceptions import ValidationError

    async def _fake_write_file(
        self, app_id: int, path: str, content: str, *, actor_user_id: int | None = None, **kwargs
    ):
        raise ValidationError("invalid", details={"code": "APP_INVALID_FILE_PATH"})

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "write_file", _fake_write_file)

    result = await live_app_tool.write_app_file.ainvoke(
        {"app_id": 10, "path": "../../bad.js", "content": "x"},
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code == "APP_INVALID_FILE_PATH"


@pytest.mark.asyncio
async def test_write_app_file_tool_returns_error_when_content_missing(runnable_config):
    result = await live_app_tool.write_app_file.ainvoke(
        {"app_id": 10, "path": "src/main.js"},
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code == "LIVE_APP_FILE_WRITE_CONTENT_REQUIRED"


@pytest.mark.asyncio
async def test_list_db_migrations_tool_returns_payload(monkeypatch, runnable_config):
    async def _fake_list_migrations(self, app_id: int, **kwargs):
        assert app_id == 11
        return {"app_id": 11, "migrations": [{"name": "001_init", "applied": False}]}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_migrations", _fake_list_migrations)

    result = await live_app_tool.list_db_migrations.ainvoke({"app_id": 11}, config=runnable_config)
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["migrations"][0]["name"] == "001_init"


@pytest.mark.asyncio
async def test_apply_db_migration_tool_maps_validation_error(monkeypatch, runnable_config):
    from apps.shared.core.exceptions import ValidationError

    async def _fake_apply_migration(
        self, app_id: int, migration_name: str, *, actor_user_id: int | None = None, **kwargs
    ):
        raise ValidationError("conflict", details={"code": "APP_MIGRATION_CONFLICT"})

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "apply_migration", _fake_apply_migration)

    result = await live_app_tool.apply_db_migration.ainvoke(
        {"app_id": 11, "migration_name": "001_init"},
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code == "APP_MIGRATION_CONFLICT"


@pytest.mark.asyncio
async def test_rollback_db_migration_tool_returns_success(monkeypatch, runnable_config):
    async def _fake_rollback_migration(
        self, app_id: int, migration_name: str, *, actor_user_id: int | None = None, **kwargs
    ):
        assert app_id == 11
        assert migration_name == "001_init"
        assert actor_user_id == 123
        return {"app_id": 11, "migration": "001_init", "rolled_back": True}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "rollback_migration", _fake_rollback_migration)

    result = await live_app_tool.rollback_db_migration.ainvoke(
        {"app_id": 11, "migration_name": "001_init"},
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["rolled_back"] is True


@pytest.mark.asyncio
async def test_create_db_migration_tool_returns_success(monkeypatch, runnable_config):
    async def _fake_create_migration(
        self,
        app_id: int,
        migration_name: str,
        up_sql: str,
        *,
        down_sql: str | None = None,
        actor_user_id: int | None = None,
        **kwargs,
    ):
        assert app_id == 12
        assert migration_name == "001_init"
        assert "CREATE TABLE" in up_sql
        assert down_sql == "DROP TABLE t;"
        assert actor_user_id == 123
        return {"app_id": 12, "migration": "001_init", "created": True}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "create_migration", _fake_create_migration)

    result = await live_app_tool.create_db_migration.ainvoke(
        {
            "app_id": 12,
            "migration_name": "001_init",
            "up_sql": "CREATE TABLE t(id INT);",
            "down_sql": "DROP TABLE t;",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["created"] is True


@pytest.mark.asyncio
async def test_remove_db_migration_tool_maps_validation_error(monkeypatch, runnable_config):
    from apps.shared.core.exceptions import ValidationError

    async def _fake_remove_migration(
        self, app_id: int, migration_name: str, *, actor_user_id: int | None = None, **kwargs
    ):
        raise ValidationError("missing", details={"code": "APP_MIGRATION_NOT_FOUND"})

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "remove_migration", _fake_remove_migration)

    result = await live_app_tool.remove_db_migration.ainvoke(
        {"app_id": 12, "migration_name": "001_init"},
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code == "APP_MIGRATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_commit_app_changes_tool_returns_success(monkeypatch, runnable_config, tmp_path):
    app_dir = tmp_path / "env" / "dev"
    app_dir.mkdir(parents=True)
    (app_dir / "app.status.md").write_text("# Status\nInitial")

    async def _fake_commit_changes(
        self,
        app_id: int,
        *,
        environment: str = "dev",
        commit_message: str | None = None,
        actor_user_id: int | None = None,
    ):
        assert app_id == 12
        assert environment == "dev"
        assert commit_message == "round commit"
        assert actor_user_id == 123
        return {"app_id": 12, "environment": "dev", "committed": True}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "commit_changes", _fake_commit_changes)
    monkeypatch.setattr(live_app_tool, "get_app_path", lambda *a, **kw: app_dir)

    result = await live_app_tool.commit_app_changes.ainvoke(
        {"app_id": 12, "message": "round commit"},
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["committed"] is True


@pytest.mark.asyncio
async def test_commit_app_changes_rejects_without_status_file(monkeypatch, runnable_config, tmp_path):
    app_dir = tmp_path / "env" / "dev"
    app_dir.mkdir(parents=True)

    monkeypatch.setattr(live_app_tool, "get_app_path", lambda *a, **kw: app_dir)

    result = await live_app_tool.commit_app_changes.ainvoke(
        {"app_id": 12, "message": "round commit"},
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "LIVE_APP_STATUS_REQUIRED"


@pytest.mark.asyncio
async def test_promote_app_environment_tool_returns_success(monkeypatch, runnable_config):
    async def _fake_promote_environment(
        self,
        app_id: int,
        *,
        from_environment: str,
        to_environment: str,
        source_commit: str | None = None,
        dry_run: bool = False,
        actor_user_id: int | None = None,
    ):
        assert app_id == 13
        assert from_environment == "dev"
        assert to_environment == "test"
        assert source_commit == "abc123"
        assert dry_run is True
        assert actor_user_id == 123
        return {"app_id": 13, "from_environment": "dev", "to_environment": "test", "promoted_files": 3}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "promote_environment", _fake_promote_environment)

    result = await live_app_tool.promote_app_environment.ainvoke(
        {"app_id": 13, "from_environment": "dev", "to_environment": "test", "source_commit": "abc123", "dry_run": True},
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["to_environment"] == "test"
    assert payload["promoted_files"] == 3


@pytest.mark.asyncio
async def test_promote_app_environment_tool_maps_validation_error(monkeypatch, runnable_config):
    from apps.shared.core.exceptions import ValidationError

    async def _fake_promote_environment(
        self,
        app_id: int,
        *,
        from_environment: str,
        to_environment: str,
        source_commit: str | None = None,
        dry_run: bool = False,
        actor_user_id: int | None = None,
    ):
        raise ValidationError("invalid transition", details={"code": "APP_INVALID_ENV_PROMOTION"})

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "promote_environment", _fake_promote_environment)

    result = await live_app_tool.promote_app_environment.ainvoke(
        {"app_id": 13, "from_environment": "dev", "to_environment": "prod"},
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code == "APP_INVALID_ENV_PROMOTION"


@pytest.mark.asyncio
async def test_list_app_commits_tool_returns_payload(monkeypatch, runnable_config):
    async def _fake_list_commits(self, app_id: int, *, environment: str = "dev", limit: int = 20):
        assert app_id == 14
        assert environment == "dev"
        assert limit == 5
        return {"app_id": 14, "environment": "dev", "commits": [{"sha": "abc", "message": "m1"}]}

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_commits", _fake_list_commits)

    result = await live_app_tool.list_app_commits.ainvoke(
        {"app_id": 14, "environment": "dev", "limit": 5},
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["commits"][0]["sha"] == "abc"


@pytest.mark.asyncio
async def test_list_app_commits_tool_maps_validation_error(monkeypatch, runnable_config):
    from apps.shared.core.exceptions import ValidationError

    async def _fake_list_commits(self, app_id: int, *, environment: str = "dev", limit: int = 20):
        raise ValidationError("dev only", details={"code": "APP_GIT_DEV_ONLY"})

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_commits", _fake_list_commits)

    result = await live_app_tool.list_app_commits.ainvoke(
        {"app_id": 14, "environment": "prod"},
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error is not None
    assert result.error.code == "APP_GIT_DEV_ONLY"


@pytest.mark.asyncio
async def test_list_app_promotions_tool_returns_payload(monkeypatch, runnable_config):
    async def _fake_list_promotions(self, app_id: int, *, limit: int = 20):
        assert app_id == 14
        assert limit == 3
        return {
            "app_id": 14,
            "promotions": [{"from_environment": "dev", "to_environment": "test", "source_commit": "abc"}],
        }

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "list_promotions", _fake_list_promotions)

    result = await live_app_tool.list_app_promotions.ainvoke(
        {"app_id": 14, "limit": 3},
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["promotions"][0]["to_environment"] == "test"


@pytest.mark.asyncio
async def test_get_app_deployment_state_tool_returns_payload(monkeypatch, runnable_config):
    async def _fake_get_deployment_state(self, app_id: int):
        assert app_id == 15
        return {
            "app_id": 15,
            "deployment_state": {"dev": "d1", "test": "t1", "prod": None},
        }

    monkeypatch.setattr(live_app_tool, "app_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(live_app_tool.LiveAppService, "get_deployment_state", _fake_get_deployment_state)

    result = await live_app_tool.get_app_deployment_state.ainvoke({"app_id": 15}, config=runnable_config)
    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["deployment_state"]["dev"] == "d1"
    assert payload["deployment_state"]["test"] == "t1"


class TestCoerceValue:
    """Unit tests for data executor type coercion."""

    from apps.shared.live_app.data_executor import _coerce_value

    coerce = staticmethod(_coerce_value)

    def test_none_passthrough(self):
        assert self.coerce(None, "integer") is None

    def test_unknown_type_passthrough(self):
        assert self.coerce("hello", "some_custom_type") == "hello"

    def test_int_from_string(self):
        assert self.coerce("42", "integer") == 42
        assert self.coerce("100", "bigint") == 100

    def test_int_passthrough(self):
        assert self.coerce(7, "integer") == 7

    def test_float_from_string(self):
        assert self.coerce("3.14", "double precision") == 3.14

    def test_decimal_from_string(self):
        from decimal import Decimal

        assert self.coerce("99.95", "numeric") == Decimal("99.95")

    def test_bool_from_string(self):
        assert self.coerce("true", "boolean") is True
        assert self.coerce("false", "boolean") is False
        assert self.coerce("1", "boolean") is True
        assert self.coerce("0", "boolean") is False

    def test_bool_passthrough(self):
        assert self.coerce(True, "boolean") is True

    def test_date_from_string(self):
        from datetime import date

        assert self.coerce("2026-04-09", "date") == date(2026, 4, 9)

    def test_date_passthrough(self):
        from datetime import date

        d = date(2026, 1, 1)
        assert self.coerce(d, "date") is d

    def test_timestamp_from_string(self):
        from datetime import datetime

        result = self.coerce("2026-04-09T12:30:00", "timestamp without time zone")
        assert isinstance(result, datetime)
        assert result.year == 2026

    def test_timestamptz_adds_utc(self):
        from datetime import timezone

        result = self.coerce("2026-04-09T12:30:00", "timestamp with time zone")
        assert result.tzinfo == timezone.utc

    def test_uuid_from_string(self):
        from uuid import UUID

        result = self.coerce("550e8400-e29b-41d4-a716-446655440000", "uuid")
        assert isinstance(result, UUID)

    def test_json_dict_serialized(self):
        result = self.coerce({"key": "val"}, "jsonb")
        assert result == '{"key": "val"}'

    def test_json_string_passthrough(self):
        assert self.coerce('{"a":1}', "jsonb") == '{"a":1}'

    def test_invalid_coercion_returns_original(self):
        assert self.coerce("not-a-number", "integer") == "not-a-number"
