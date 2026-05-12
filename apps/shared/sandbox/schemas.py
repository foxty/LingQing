"""Shared Pydantic schemas for sandbox execute requests and responses."""

from pydantic import BaseModel, Field


class SandboxExecuteRequestContext(BaseModel):
    """Typed execution context for sandbox mount resolution and tracing."""

    tenant_id: int = Field(..., gt=0)
    user_id: int = Field(..., gt=0)
    thread_id: str = Field(...)
    session_id: str = Field(...)
    agent_id: int = Field(...)
    tool_name: str = Field(...)
    command_hash: str = Field(...)
    app_root_subpath: str | None = None
    extra_env_vars: dict[str, str] | None = Field(
        default=None,
        description="Extra environment variables to inject into the sandbox container (方案A: passed via -e flags).",
    )


class SandboxExecuteRequest(BaseModel):
    """Execution request for sandbox bash command."""

    command: str = Field(..., min_length=1)
    timeout_seconds: int = Field(default=15, ge=1, le=600)
    working_dir: str = Field(
        default="/workspace",
        description="Container workdir ('/workspace' or '/app_root' when app_root_subpath is provided).",
    )
    output_max_bytes: int | None = Field(default=None, ge=1, le=1048576)
    request_context: SandboxExecuteRequestContext = Field(...)


class SandboxExecuteResult(BaseModel):
    """Execution result from sandbox bash command."""

    exit_code: int
    timed_out: bool
    duration_ms: int
    workspace_path: str
    app_root_path: str | None = None
    skills_root_path: str
    skill_packages_root_path: str
    tenant_skills_root_path: str | None = None
    tenant_skill_packages_root_path: str | None = None
    failure_stage: str | None = None
    stdout: str
    stderr: str
    output_truncated: bool


class SandboxExecuteResponse(BaseModel):
    """Response from sandbox bash execution endpoint."""

    ok: bool = True
    request_id: str
    result: SandboxExecuteResult


class SandboxHealthResponse(BaseModel):
    """Response from sandbox health check endpoint."""

    status: str = "ok"
    runner_image: str
    max_parallel_workers: int
