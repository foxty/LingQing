"""Sandbox controller service for controlled bash execution."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException

from apps.sandbox_service.skill_packages import SkillPackageInstaller, build_skill_pythonpath_preamble
from apps.shared.sandbox.paths import (
    get_skill_packages_dir,
    get_tenant_bash_workspace_dir,
    get_tenant_skill_packages_dir,
    get_tenant_skills_dir,
)
from apps.shared.sandbox.schemas import (
    SandboxExecuteRequest,
    SandboxExecuteRequestContext,
    SandboxExecuteResponse,
    SandboxExecuteResult,
    SandboxHealthResponse,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)


def _read_env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name)
    if value is not None:
        value = value.strip()
    if not value:
        if required:
            raise RuntimeError(f"Missing required environment variable: {name}")
        if default is not None:
            return default
        return ""
    return value


def _read_int_env(name: str, *, min_value: int | None = None) -> int:
    raw = _read_env(name, required=True)
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer, got: {raw}") from exc
    if min_value is not None and value < min_value:
        raise RuntimeError(f"Environment variable {name} must be >= {min_value}, got: {value}")
    return value


RUNNER_IMAGE = _read_env("SANDBOX_RUNNER_IMAGE", required=True)
MAX_TIMEOUT_SECONDS = _read_int_env("SANDBOX_MAX_TIMEOUT_SECONDS", min_value=1)
DEFAULT_OUTPUT_MAX_BYTES = _read_int_env("SANDBOX_OUTPUT_MAX_BYTES", min_value=1)
MAX_COMMAND_CHARS = _read_int_env("SANDBOX_MAX_COMMAND_CHARS", min_value=1)
MAX_PARALLEL_WORKERS = _read_int_env("SANDBOX_MAX_PARALLEL_WORKERS", min_value=1)
MAX_QUEUE_SIZE = _read_int_env("SANDBOX_MAX_QUEUE_SIZE", min_value=1)
PER_TENANT_PARALLEL_LIMIT = _read_int_env("SANDBOX_PER_TENANT_PARALLEL_LIMIT", min_value=1)

CPU_LIMIT = _read_env("SANDBOX_RUNNER_CPU_LIMIT", required=True)
MEMORY_LIMIT = _read_env("SANDBOX_RUNNER_MEMORY_LIMIT", required=True)
PIDS_LIMIT = _read_env("SANDBOX_RUNNER_PIDS_LIMIT", required=True)
NETWORK_MODE = _read_env("SANDBOX_RUNNER_NETWORK_MODE", required=True)
WORKSPACE_DATA_ROOT = _read_env("DATA_ROOT_PATH", required=True)
# Optional env vars forwarded into sandbox runner containers.
RUNNER_PASSTHROUGH_ENV: list[tuple[str, str]] = [
    ("SSL_NO_VERIFY", _read_env("SANDBOX_RUNNER_SSL_NO_VERIFY", default="")),
]


def _expand_optional_absolute_host_path(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    expanded = os.path.expanduser(text)
    if not os.path.isabs(expanded):
        return ""
    return expanded


# Dev/e2e/prod: host dir bound to DATA_ROOT_PATH; nested docker bind sources must use this path (~ expanded).
DATA_ROOT_HOST_PATH = _expand_optional_absolute_host_path(_read_env("DATA_ROOT_HOST_PATH", required=True))

DENY_PATTERNS = (
    "docker ",
    "/var/run/docker.sock",
    "--privileged",
    "mount ",
)

app = FastAPI(title="Sandbox Controller", version="1.0.0")

_global_semaphore = asyncio.Semaphore(MAX_PARALLEL_WORKERS)
_tenant_semaphores: dict[str, asyncio.Semaphore] = defaultdict(lambda: asyncio.Semaphore(PER_TENANT_PARALLEL_LIMIT))
_queue_lock = asyncio.Lock()
_pending_count = 0


def _truncate_output(raw: bytes, max_bytes: int) -> tuple[str, bool]:
    if len(raw) <= max_bytes:
        return raw.decode("utf-8", errors="replace"), False
    return raw[:max_bytes].decode("utf-8", errors="replace"), True


def _first_line(text: str) -> str:
    line = (text or "").strip().splitlines()
    return line[0] if line else ""


def _validate_request(req: SandboxExecuteRequest) -> None:
    if len(req.command) > MAX_COMMAND_CHARS:
        raise HTTPException(status_code=400, detail=f"Command too long (>{MAX_COMMAND_CHARS} chars).")
    if req.working_dir not in {"/workspace", "/app_root"}:
        raise HTTPException(status_code=400, detail="working_dir must be '/workspace' or '/app_root'.")
    if req.working_dir == "/app_root" and not req.request_context.app_root_subpath:
        raise HTTPException(status_code=400, detail="working_dir '/app_root' requires app_root_subpath.")

    lowered = req.command.lower()
    for pattern in DENY_PATTERNS:
        if pattern in lowered:
            raise HTTPException(status_code=400, detail=f"Command rejected by policy pattern: {pattern}")


def _sanitize_mount_subpath(value: Any, *, field_name: str) -> str:
    text = str(value or "").strip().strip("/")
    if not text:
        raise HTTPException(status_code=400, detail=f"{field_name} must not be empty.")
    if "\\" in text:
        raise HTTPException(status_code=400, detail=f"{field_name} must use POSIX-style paths.")
    if text.startswith("../") or text == ".." or "/../" in f"/{text}/":
        raise HTTPException(status_code=400, detail=f"{field_name} must not contain parent traversal.")
    if not re.fullmatch(r"[a-zA-Z0-9._/-]+", text):
        raise HTTPException(status_code=400, detail=f"{field_name} contains invalid characters.")
    return text


def _docker_bind_src(container_path: str) -> str:
    """Map in-container DATA_ROOT path to host path for Docker bind mounts (nested docker).

    When unset, production uses the same path on host and container (e.g. /var/lib/lingqing/data).
    Uses normpath (not resolve) so symlinks under DATA_ROOT are preserved as-is and mapped
    correctly to the host path without following symlink targets.
    """
    host_root = (DATA_ROOT_HOST_PATH or "").strip()
    if not host_root:
        return container_path
    try:
        root = Path(os.path.normpath(WORKSPACE_DATA_ROOT))
        ap = Path(os.path.normpath(container_path))
        rel = ap.relative_to(root)
    except ValueError:
        return container_path
    host_base = Path(host_root)
    if not host_base.is_absolute():
        return container_path
    return str(host_base / rel)


def _resolve_optional_app_root(request_context: SandboxExecuteRequestContext) -> str | None:
    app_root_subpath = request_context.app_root_subpath
    if not app_root_subpath:
        return None
    root_abs = os.path.abspath(WORKSPACE_DATA_ROOT)
    rel_path = _sanitize_mount_subpath(app_root_subpath, field_name="app_root_subpath")
    app_root_path = os.path.abspath(os.path.join(root_abs, rel_path))
    if app_root_path != root_abs and not app_root_path.startswith(f"{root_abs}{os.sep}"):
        raise HTTPException(status_code=400, detail="Invalid app root path resolution.")
    return app_root_path


def _resolve_skills_root() -> str:
    """Resolve host path for the static /skills mount (always present)."""
    return os.path.abspath(os.path.join(WORKSPACE_DATA_ROOT, "skills"))


def _resolve_skill_packages_root() -> str:
    """Resolve host path for shared skill package cache mount."""
    return get_skill_packages_dir(WORKSPACE_DATA_ROOT)


def _resolve_tenant_skills_root(tenant_id: int) -> str | None:
    """Resolve host path for tenant-scoped skills, or None if dir doesn't exist."""
    path = get_tenant_skills_dir(WORKSPACE_DATA_ROOT, tenant_id)
    return path if os.path.isdir(path) else None


def _resolve_tenant_skill_packages_root(tenant_id: int) -> str:
    """Resolve host path for tenant-scoped skill package cache."""
    return get_tenant_skill_packages_dir(WORKSPACE_DATA_ROOT, tenant_id)


async def _ensure_host_dir(path: str) -> None:
    # Skip makedirs if the path is already a symlink (e.g. dev symlink into repo);
    # makedirs with exist_ok=True raises when the symlink target is not a real directory.
    if os.path.islink(path):
        return
    await asyncio.to_thread(os.makedirs, path, mode=0o755, exist_ok=True)


_skill_package_installer = SkillPackageInstaller(
    runner_image=RUNNER_IMAGE,
    network_mode=NETWORK_MODE,
    cpu_limit=CPU_LIMIT,
    memory_limit=MEMORY_LIMIT,
    pids_limit=PIDS_LIMIT,
    docker_bind_src=_docker_bind_src,
)


async def _increment_pending() -> None:
    global _pending_count
    async with _queue_lock:
        if _pending_count >= MAX_QUEUE_SIZE:
            raise HTTPException(status_code=503, detail="Sandbox queue is full.")
        _pending_count += 1


async def _decrement_pending() -> None:
    global _pending_count
    async with _queue_lock:
        _pending_count = max(0, _pending_count - 1)


async def _force_remove_container(container_name: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "docker",
        "rm",
        "-f",
        container_name,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await process.communicate()


async def _run_in_ephemeral_container(
    request_id: str,
    req: SandboxExecuteRequest,
) -> SandboxExecuteResult:
    """Execute command in ephemeral Docker container.

    Returns:
        SandboxExecuteResult with execution outcome
    """
    timeout_seconds = min(req.timeout_seconds, MAX_TIMEOUT_SECONDS)
    output_max_bytes = min(req.output_max_bytes or DEFAULT_OUTPUT_MAX_BYTES, DEFAULT_OUTPUT_MAX_BYTES)
    container_name = f"sandbox-{request_id[:12]}"
    host_workspace_path = get_tenant_bash_workspace_dir(
        WORKSPACE_DATA_ROOT, req.request_context.tenant_id, req.request_context.user_id
    )
    await _ensure_host_dir(host_workspace_path)
    host_app_root_path = _resolve_optional_app_root(req.request_context)
    host_skills_root_path = _resolve_skills_root()
    host_skill_packages_root_path = _resolve_skill_packages_root()
    host_tenant_skills_root_path = _resolve_tenant_skills_root(req.request_context.tenant_id)
    host_tenant_skill_packages_root_path = None
    if host_tenant_skills_root_path:
        host_tenant_skill_packages_root_path = _resolve_tenant_skill_packages_root(req.request_context.tenant_id)
        await _ensure_host_dir(host_tenant_skill_packages_root_path)
    if host_app_root_path:
        await _ensure_host_dir(host_app_root_path)
    await _ensure_host_dir(host_skills_root_path)
    # Eagerly install skill packages at container start
    await _skill_package_installer.ensure_skill_packages(host_skills_root_path, host_skill_packages_root_path)
    if host_tenant_skills_root_path:
        await _skill_package_installer.ensure_skill_packages(
            host_tenant_skills_root_path, host_tenant_skill_packages_root_path
        )

    logger.info(
        "Sandbox launch context request_id=%s tenant=%s user=%s thread=%s session=%s tool=%s command_hash=%s "
        "working_dir=%s workspace_bind=%s app_root_bind=%s skills_bind=%s skill_packages_bind=%s "
        "tenant_skills_bind=%s tenant_skill_packages_bind=%s app_root_subpath=%s",
        request_id,
        req.request_context.tenant_id,
        req.request_context.user_id,
        req.request_context.thread_id,
        req.request_context.session_id,
        req.request_context.tool_name,
        req.request_context.command_hash,
        req.working_dir,
        host_workspace_path,
        host_app_root_path,
        host_skills_root_path,
        host_skill_packages_root_path,
        host_tenant_skills_root_path or "disabled",
        host_tenant_skill_packages_root_path or "disabled",
        req.request_context.app_root_subpath,
    )

    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        "--network",
        NETWORK_MODE,
        "--cpus",
        CPU_LIMIT,
        "--memory",
        MEMORY_LIMIT,
        "--pids-limit",
        PIDS_LIMIT,
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m",
        "--mount",
        f"type=bind,src={_docker_bind_src(host_workspace_path)},dst=/workspace",
        "--mount",
        f"type=bind,src={_docker_bind_src(host_skills_root_path)},dst=/skills,readonly",
        "--mount",
        f"type=bind,src={_docker_bind_src(host_skill_packages_root_path)},dst=/skill-packages,readonly",
    ]
    if host_tenant_skills_root_path:
        docker_cmd.extend(
            [
                "--mount",
                f"type=bind,src={_docker_bind_src(host_tenant_skills_root_path)},dst=/skills-tenant,readonly",
            ]
        )
    if host_tenant_skill_packages_root_path:
        docker_cmd.extend(
            [
                "--mount",
                f"type=bind,src={_docker_bind_src(host_tenant_skill_packages_root_path)},dst=/skill-packages-tenant,readonly",
            ]
        )
    for env_name, env_value in RUNNER_PASSTHROUGH_ENV:
        if env_value:
            docker_cmd.extend(["-e", f"{env_name}={env_value}"])
    extra_env = req.request_context.extra_env_vars
    if extra_env:
        for env_name, env_value in extra_env.items():
            docker_cmd.extend(["-e", f"{env_name}={env_value}"])
    if host_app_root_path:
        docker_cmd.extend(
            [
                "--mount",
                f"type=bind,src={_docker_bind_src(host_app_root_path)},dst=/app_root",
            ]
        )
    docker_cmd.extend(
        [
            "--workdir",
            req.working_dir,
            "--user",
            "1000:1000",
            "-e",
            "PYTHONUNBUFFERED=1",
            RUNNER_IMAGE,
            "/bin/bash",
            "-lc",
            build_skill_pythonpath_preamble() + req.command,
        ]
    )

    logger.info(
        "Sandbox docker mounts request_id=%s workspace_mount=%s app_root_mount=%s skills_mount=%s "
        "skill_packages_mount=%s tenant_skills_mount=%s tenant_skill_packages_mount=%s image=%s network=%s",
        request_id,
        f"type=bind,src={host_workspace_path},dst=/workspace",
        (f"type=bind,src={host_app_root_path},dst=/app_root" if host_app_root_path else "disabled"),
        f"type=bind,src={host_skills_root_path},dst=/skills,readonly",
        f"type=bind,src={host_skill_packages_root_path},dst=/skill-packages,readonly",
        (
            f"type=bind,src={host_tenant_skills_root_path},dst=/skills-tenant,readonly"
            if host_tenant_skills_root_path
            else "disabled"
        ),
        (
            f"type=bind,src={host_tenant_skill_packages_root_path},dst=/skill-packages-tenant,readonly"
            if host_tenant_skill_packages_root_path
            else "disabled"
        ),
        RUNNER_IMAGE,
        NETWORK_MODE,
    )

    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *docker_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    timed_out = False
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds + 1)
        exit_code = process.returncode
    except TimeoutError:
        timed_out = True
        await _force_remove_container(container_name)
        exit_code = -1
        stdout_bytes = b""
        stderr_bytes = f"Command timed out after {timeout_seconds}s.".encode()

    stdout_text, stdout_truncated = _truncate_output(stdout_bytes, output_max_bytes)
    stderr_text, stderr_truncated = _truncate_output(stderr_bytes, output_max_bytes)

    duration_ms = int((time.monotonic() - started) * 1000)
    if exit_code == 125 and not timed_out:
        logger.error(
            "Sandbox runner launch failed request_id=%s container=%s image=%s network=%s workspace=%s stderr=%s",
            request_id,
            container_name,
            RUNNER_IMAGE,
            NETWORK_MODE,
            host_workspace_path,
            _first_line(stderr_text),
        )

    return SandboxExecuteResult(
        exit_code=exit_code,
        timed_out=timed_out,
        duration_ms=duration_ms,
        workspace_path=host_workspace_path,
        app_root_path=host_app_root_path,
        skills_root_path=host_skills_root_path,
        skill_packages_root_path=host_skill_packages_root_path,
        tenant_skills_root_path=host_tenant_skills_root_path,
        tenant_skill_packages_root_path=host_tenant_skill_packages_root_path,
        failure_stage="container_start" if exit_code == 125 and not timed_out else None,
        stdout=stdout_text,
        stderr=stderr_text,
        output_truncated=stdout_truncated or stderr_truncated,
    )


@app.get("/health", response_model=SandboxHealthResponse)
async def health() -> SandboxHealthResponse:
    """Health check endpoint."""
    return SandboxHealthResponse(
        status="ok",
        runner_image=RUNNER_IMAGE,
        max_parallel_workers=MAX_PARALLEL_WORKERS,
    )


@app.post("/execute/bash", response_model=SandboxExecuteResponse)
async def execute_bash(req: SandboxExecuteRequest) -> SandboxExecuteResponse:
    """Execute bash command in ephemeral sandbox container."""
    _validate_request(req)
    request_id = uuid4().hex
    tenant_key = str(req.request_context.tenant_id)

    await _increment_pending()
    try:
        tenant_semaphore = _tenant_semaphores[tenant_key]
        async with _global_semaphore, tenant_semaphore:
            result = await _run_in_ephemeral_container(request_id=request_id, req=req)
    finally:
        await _decrement_pending()

    logger.info(
        "Sandbox request finished request_id=%s command=%s tenant=%s exit_code=%s timed_out=%s duration_ms=%s",
        request_id,
        req.command,
        tenant_key,
        result.exit_code,
        result.timed_out,
        result.duration_ms,
    )
    return SandboxExecuteResponse(
        ok=True,
        request_id=request_id,
        result=result,
    )
