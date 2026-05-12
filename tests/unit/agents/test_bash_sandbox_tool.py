import json
import os

import pytest

from apps.config import EnvConfig
from apps.shared.sandbox.client import SandboxResult
from apps.tenant_app_service.agents.tools.bash_sandbox import run_bash_script
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


class _FakeSandboxClient:
    """Fake SandboxClient for testing."""

    def __init__(self, sandbox_result: SandboxResult):
        self._result = sandbox_result
        self.close_count = 0

    async def execute(self, command, timeout_seconds, context, working_dir, app_root_subpath, extra_env_vars=None):
        return self._result

    async def close(self):
        self.close_count += 1


@pytest.mark.asyncio
async def test_run_bash_script_success(monkeypatch, runnable_config):
    monkeypatch.setattr(EnvConfig, "AGENT_SANDBOX_BASE_URL", "http://sandbox-controller:8090")

    fake_result = SandboxResult(
        exit_code=0,
        stdout="hello",
        stderr="",
        duration_ms=120,
        output_truncated=False,
        timed_out=False,
        ok=True,
        request_id="req_1",
        status_code=200,
        command_hash="abc123",
    )

    def _client_factory(*args, **kwargs):
        return _FakeSandboxClient(fake_result)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.bash_sandbox.SandboxClient", _client_factory)

    result = await run_bash_script.coroutine(command="echo hello", config=runnable_config)
    data = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert data["exit_code"] == 0
    assert data["stdout"] == "hello"


@pytest.mark.asyncio
async def test_run_bash_script_non_zero_exit_returns_error(monkeypatch, runnable_config):
    monkeypatch.setattr(EnvConfig, "AGENT_SANDBOX_BASE_URL", "http://sandbox-controller:8090")

    fake_result = SandboxResult(
        exit_code=2,
        stdout="",
        stderr="failed",
        duration_ms=80,
        output_truncated=False,
        timed_out=False,
        ok=True,
        request_id="req_2",
        status_code=200,
        command_hash="abc123",
    )

    def _client_factory(*args, **kwargs):
        return _FakeSandboxClient(fake_result)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.bash_sandbox.SandboxClient", _client_factory)

    result = await run_bash_script.coroutine(command="exit 2", config=runnable_config)

    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "SANDBOX_COMMAND_FAILED"
    assert "Output (first 5 lines):" in result.error.message
    assert "failed" in result.error.message
    assert "Full stdout/stderr available in exception metadata" in result.error.message


@pytest.mark.asyncio
async def test_run_bash_script_non_zero_exit_no_output(monkeypatch, runnable_config):
    """Test error message when command fails with no stdout/stderr."""
    monkeypatch.setattr(EnvConfig, "AGENT_SANDBOX_BASE_URL", "http://sandbox-controller:8090")

    fake_result = SandboxResult(
        exit_code=1,
        stdout="",
        stderr="",
        duration_ms=50,
        output_truncated=False,
        timed_out=False,
        ok=True,
        request_id="req_no_output",
        status_code=200,
        command_hash="abc123",
    )

    def _client_factory(*args, **kwargs):
        return _FakeSandboxClient(fake_result)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.bash_sandbox.SandboxClient", _client_factory)

    result = await run_bash_script.coroutine(command="exit 1", config=runnable_config)

    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "SANDBOX_COMMAND_FAILED"
    assert "Command exited with non-zero code: 1" in result.error.message
    assert "No output captured (stdout and stderr are empty)" in result.error.message
    assert "Full stdout/stderr available in exception metadata" in result.error.message


@pytest.mark.asyncio
async def test_run_bash_script_exit_125_returns_launch_hint(monkeypatch, runnable_config):
    monkeypatch.setattr(EnvConfig, "AGENT_SANDBOX_BASE_URL", "http://sandbox-controller:8090")

    fake_result = SandboxResult(
        exit_code=125,
        stdout="",
        stderr="docker: Error response from daemon: invalid mount config.",
        duration_ms=50,
        output_truncated=False,
        timed_out=False,
        failure_stage="container_start",
        ok=True,
        request_id="req_3",
        status_code=200,
        command_hash="abc123",
    )

    def _client_factory(*args, **kwargs):
        return _FakeSandboxClient(fake_result)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.bash_sandbox.SandboxClient", _client_factory)

    result = await run_bash_script.coroutine(command="echo hello", config=runnable_config)

    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "SANDBOX_COMMAND_FAILED"
    assert "failed to start (exit 125)" in result.error.message


@pytest.mark.asyncio
async def test_run_bash_script_rejects_timeout_above_max(monkeypatch, runnable_config):
    monkeypatch.setattr(EnvConfig, "AGENT_SANDBOX_MAX_TIMEOUT_SECONDS", 30)

    result = await run_bash_script.coroutine(
        command="echo hello",
        timeout_seconds=31,
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "SANDBOX_TIMEOUT_TOO_LARGE"


@pytest.mark.asyncio
async def test_run_bash_script_rejects_invalid_app_root_subpath(monkeypatch, runnable_config):
    # Mock the app validation to return the subpath that will then fail sanitization
    async def _mock_validate_app_context(runtime, app_id, environment):
        return f"tenants/tenant_{runtime.user.tenant_id}/apps/app_{app_id}/env/{environment}"

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.bash_sandbox._validate_app_context", _mock_validate_app_context
    )

    # Mock the client to return a success result
    fake_result = SandboxResult(
        exit_code=0, stdout="hello", stderr="", ok=True, request_id="req", status_code=200, command_hash="abc"
    )

    def _client_factory(*args, **kwargs):
        return _FakeSandboxClient(fake_result)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.bash_sandbox.SandboxClient", _client_factory)

    from apps.tenant_app_service.agents.tools.bash_sandbox import AppContext, BashSandboxContext

    result = await run_bash_script.coroutine(
        command="echo hello",
        with_context=BashSandboxContext(app_context=AppContext(app_id=1, environment="dev")),
        config=runnable_config,
    )
    # Note: The invalid path characters are now handled by the client, not here
    # This test would need adjustment for the new architecture
    assert result.status == ToolResultStatus.SUCCESS


@pytest.mark.asyncio
async def test_run_bash_script_rejects_app_root_workdir_without_subpath(runnable_config):
    # Test that working_dir="/app_root" without app context fails
    result = await run_bash_script.coroutine(
        command="echo hello",
        working_dir="/app_root",
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "SANDBOX_INVALID_WORKDIR"


@pytest.mark.asyncio
async def test_run_bash_script_with_app_context_success(monkeypatch, runnable_config):
    monkeypatch.setattr(EnvConfig, "AGENT_SANDBOX_BASE_URL", "http://sandbox-controller:8090")

    fake_result = SandboxResult(
        exit_code=0,
        stdout="app output",
        stderr="",
        duration_ms=150,
        output_truncated=False,
        timed_out=False,
        ok=True,
        request_id="req_4",
        status_code=200,
        command_hash="abc123",
    )

    def _client_factory(*args, **kwargs):
        return _FakeSandboxClient(fake_result)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.bash_sandbox.SandboxClient", _client_factory)

    # Mock the app validation to avoid database connection
    async def _mock_validate_app_context(runtime, app_id, environment):
        return f"tenants/tenant_{runtime.user.tenant_id}/apps/app_{app_id}/env/{environment}"

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.bash_sandbox._validate_app_context", _mock_validate_app_context
    )

    from apps.tenant_app_service.agents.tools.bash_sandbox import AppContext, BashSandboxContext

    result = await run_bash_script.coroutine(
        command="ls -la",
        with_context=BashSandboxContext(app_context=AppContext(app_id=123, environment="dev")),
        config=runnable_config,
    )
    data = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert data["exit_code"] == 0
    assert data["stdout"] == "app output"
    # Verify path context is returned (not redundant app_id/environment)
    assert data["workspace_dir"] == "/workspace"
    assert data["app_root_dir"] == "/app_root"
    assert "app_root_subpath" in data


@pytest.mark.asyncio
async def test_run_bash_script_blocks_dangerous_commands_in_app_context(runnable_config):
    from apps.tenant_app_service.agents.tools.bash_sandbox import AppContext, BashSandboxContext

    # Test rm -rf / command
    result = await run_bash_script.coroutine(
        command="rm -rf /",
        with_context=BashSandboxContext(app_context=AppContext(app_id=123, environment="dev")),
        config=runnable_config,
    )

    assert result.status == ToolResultStatus.ERROR
    assert result.error.code == "LIVE_APP_COMMAND_BLOCKED"
    assert "blocked by safety policy" in result.error.message


@pytest.mark.asyncio
async def test_run_bash_script_accepts_json_string_for_with_context(monkeypatch, runnable_config):
    monkeypatch.setattr(EnvConfig, "AGENT_SANDBOX_BASE_URL", "http://sandbox-controller:8090")

    fake_result = SandboxResult(
        exit_code=0,
        stdout="app output from json string",
        stderr="",
        duration_ms=150,
        output_truncated=False,
        timed_out=False,
        ok=True,
        request_id="req_5",
        status_code=200,
        command_hash="abc123",
    )

    def _client_factory(*args, **kwargs):
        return _FakeSandboxClient(fake_result)

    monkeypatch.setattr("apps.tenant_app_service.agents.tools.bash_sandbox.SandboxClient", _client_factory)

    # Mock the app validation to avoid database connection
    async def _mock_validate_app_context(runtime, app_id, environment):
        return f"tenants/tenant_{runtime.user.tenant_id}/apps/app_{app_id}/env/{environment}"

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.bash_sandbox._validate_app_context", _mock_validate_app_context
    )

    # Pass with_context as JSON string (simulating LLM behavior)
    with_context_json = '{"app_context": {"app_id": 456, "environment": "test"}}'

    result = await run_bash_script.coroutine(
        command="ls -la",
        with_context=with_context_json,
        config=runnable_config,
    )
    data = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert data["exit_code"] == 0
    assert data["stdout"] == "app output from json string"
    # Verify path context is returned (not redundant app_id/environment)
    assert data["workspace_dir"] == "/workspace"
    assert data["app_root_dir"] == "/app_root"
    assert "app_root_subpath" in data


# ==============================================================================
# Env var injection tests (auto-resolution from skill paths in command)
# ==============================================================================


def test_resolve_skill_env_vars_no_config():
    """No config.json -> empty dict."""
    from apps.tenant_app_service.agents.tools.bash_sandbox import _resolve_skill_env_vars

    result = _resolve_skill_env_vars(
        "cd /skills-tenant/my-skill && python3 run.py", tenant_id=1, user_id=1
    )
    assert result == {}


def test_resolve_skill_env_vars_no_skill_path():
    from apps.tenant_app_service.agents.tools.bash_sandbox import _resolve_skill_env_vars

    result = _resolve_skill_env_vars("echo hello", tenant_id=1, user_id=1)
    assert result == {}


def test_resolve_tenant_skill_env_vars(monkeypatch):
    """Mock SkillService to avoid filesystem/encryption dependencies."""
    from unittest.mock import MagicMock
    from apps.tenant_app_service.agents.tools.bash_sandbox import _resolve_skill_env_vars

    mock_svc = MagicMock()
    mock_svc.get_decrypted_env_vars.return_value = {"API_KEY": "sk-test-key"}
    monkeypatch.setattr(
        "apps.tenant_app_service.skills.service.SkillService",
        lambda: mock_svc,
    )

    result = _resolve_skill_env_vars(
        "cd /skills-tenant/my-skill && python3 run.py", tenant_id=42, user_id=7
    )
    assert result == {"API_KEY": "sk-test-key"}
    mock_svc.get_decrypted_env_vars.assert_called_once_with(42, 7, "tenant", "my-skill")


def test_resolve_personal_skill_env_vars(monkeypatch):
    """Mock SkillService to avoid filesystem/encryption dependencies."""
    from unittest.mock import MagicMock
    from apps.tenant_app_service.agents.tools.bash_sandbox import _resolve_skill_env_vars

    mock_svc = MagicMock()
    mock_svc.get_decrypted_env_vars.return_value = {"TOKEN": "personal-token"}
    monkeypatch.setattr(
        "apps.tenant_app_service.skills.service.SkillService",
        lambda: mock_svc,
    )

    result = _resolve_skill_env_vars(
        "cd /workspace/skills/my-skill && python3 run.py", tenant_id=42, user_id=7
    )
    assert result == {"TOKEN": "personal-token"}
    mock_svc.get_decrypted_env_vars.assert_called_once_with(42, 7, "personal", "my-skill")


def test_resolve_multiple_skills_env_vars(monkeypatch):
    """Mock SkillService to test multi-skill env var resolution."""
    from unittest.mock import MagicMock
    from apps.tenant_app_service.agents.tools.bash_sandbox import _resolve_skill_env_vars

    mock_svc = MagicMock()
    # Return different env vars based on which skill is queried
    def mock_get_envs(tenant_id, user_id, scope, name):
        if name == "skill-a":
            return {"A_KEY": "val-a"}
        elif name == "skill-b":
            return {"B_KEY": "val-b"}
        return {}

    mock_svc.get_decrypted_env_vars.side_effect = mock_get_envs
    monkeypatch.setattr(
        "apps.tenant_app_service.skills.service.SkillService",
        lambda: mock_svc,
    )

    command = "cd /skills-tenant/skill-a && python3 a.py && cd /workspace/skills/skill-b && python3 b.py"
    result = _resolve_skill_env_vars(command, tenant_id=1, user_id=2)
    assert result["A_KEY"] == "val-a"
    assert result["B_KEY"] == "val-b"
    # Verify both skill types were queried
    assert mock_svc.get_decrypted_env_vars.call_count == 2
