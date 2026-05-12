from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def _build_request_payload(*, working_dir: str = "/workspace", app_root_subpath: str | None = None) -> dict:
    return {
        "command": "echo hello",
        "timeout_seconds": 5,
        "working_dir": working_dir,
        "request_context": {
            "tenant_id": 1,
            "user_id": 2,
            "thread_id": "t-1",
            "session_id": "s-1",
            "agent_id": 3,
            "tool_name": "run_bash_script",
            "command_hash": "abc123",
            "app_root_subpath": app_root_subpath,
        },
    }


@pytest.fixture
def sandbox_server_module(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    data_root = tmp_path / "data-root"
    data_root.mkdir(parents=True, exist_ok=True)

    env = {
        "SANDBOX_RUNNER_IMAGE": "python:3.11-slim",
        "SANDBOX_MAX_TIMEOUT_SECONDS": "60",
        "SANDBOX_OUTPUT_MAX_BYTES": "65536",
        "SANDBOX_MAX_COMMAND_CHARS": "4096",
        "SANDBOX_MAX_PARALLEL_WORKERS": "4",
        "SANDBOX_MAX_QUEUE_SIZE": "100",
        "SANDBOX_PER_TENANT_PARALLEL_LIMIT": "2",
        "SANDBOX_RUNNER_CPU_LIMIT": "0.5",
        "SANDBOX_RUNNER_MEMORY_LIMIT": "256m",
        "SANDBOX_RUNNER_PIDS_LIMIT": "64",
        "SANDBOX_RUNNER_NETWORK_MODE": "bridge",
        "DATA_ROOT_PATH": str(data_root),
        "DATA_ROOT_HOST_PATH": str(data_root),
        "SANDBOX_RUNNER_SSL_NO_VERIFY": "",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import apps.sandbox_service.server as server_module

    return importlib.reload(server_module)


@pytest.mark.asyncio
async def test_execute_bash_http_wires_installer_and_mounts_skill_packages(
    monkeypatch: pytest.MonkeyPatch, sandbox_server_module
) -> None:
    recorded_cmds: list[list[str]] = []
    installer_calls: list[tuple[str, str]] = []

    async def _fake_ensure_skill_packages(skills_root: str, packages_root: str) -> None:
        installer_calls.append((skills_root, packages_root))

    class _FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"hello\n", b""

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        recorded_cmds.append([str(part) for part in cmd])
        return _FakeProcess()

    monkeypatch.setattr(
        sandbox_server_module._skill_package_installer,
        "ensure_skill_packages",
        _fake_ensure_skill_packages,
    )
    monkeypatch.setattr(
        sandbox_server_module.asyncio,
        "create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    client = TestClient(sandbox_server_module.app)
    response = client.post("/execute/bash", json=_build_request_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["exit_code"] == 0
    assert len(installer_calls) == 1

    docker_cmd = recorded_cmds[0]
    docker_cmd_text = " ".join(docker_cmd)
    assert "dst=/skill-packages,readonly" in docker_cmd_text
    assert "dst=/skills,readonly" in docker_cmd_text

    shell_command = docker_cmd[-1]
    assert 'export PYTHONPATH="$__pkg_root/$__sn/python' in shell_command
    assert "/skills-tenant" in shell_command
    assert "/workspace/skills" in shell_command
    assert "echo hello" in shell_command


@pytest.mark.asyncio
async def test_execute_bash_http_includes_app_root_mount_when_requested(
    monkeypatch: pytest.MonkeyPatch, sandbox_server_module
) -> None:
    recorded_cmds: list[list[str]] = []

    async def _fake_ensure_skill_packages(skills_root: str, packages_root: str) -> None:
        return None

    class _FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"ok\n", b""

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        recorded_cmds.append([str(part) for part in cmd])
        return _FakeProcess()

    monkeypatch.setattr(
        sandbox_server_module._skill_package_installer,
        "ensure_skill_packages",
        _fake_ensure_skill_packages,
    )
    monkeypatch.setattr(
        sandbox_server_module.asyncio,
        "create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    client = TestClient(sandbox_server_module.app)
    response = client.post(
        "/execute/bash",
        json=_build_request_payload(
            working_dir="/app_root",
            app_root_subpath="tenants/tenant_1/apps/app_2/env/dev",
        ),
    )

    assert response.status_code == 200
    docker_cmd_text = " ".join(recorded_cmds[0])
    assert "dst=/app_root" in docker_cmd_text


@pytest.mark.asyncio
async def test_execute_bash_http_returns_500_when_installer_fails(
    monkeypatch: pytest.MonkeyPatch, sandbox_server_module
) -> None:
    async def _failing_ensure_skill_packages(skills_root: str, packages_root: str) -> None:
        raise HTTPException(status_code=500, detail="install failed")

    monkeypatch.setattr(
        sandbox_server_module._skill_package_installer,
        "ensure_skill_packages",
        _failing_ensure_skill_packages,
    )

    client = TestClient(sandbox_server_module.app)
    response = client.post("/execute/bash", json=_build_request_payload())

    assert response.status_code == 500
    assert response.json()["detail"] == "install failed"
