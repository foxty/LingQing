"""Sandboxed bash execution tool.

This module provides the run_bash_script tool for agent execution.
Sandbox communication is delegated to SandboxClient in shared/sandbox/client.py.
"""

from __future__ import annotations

import json
import re

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.live_app.service import LiveAppService
from apps.shared.sandbox.client import (
    SandboxClient,
    SandboxError,
    SandboxExecutionContext,
    SandboxResult,
    SandboxValidationError,
    _build_non_zero_exit_message,
)
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolError, ToolResult, ToolResultStatus

logger = get_logger(__name__)


class AppContext(BaseModel):
    """Context for app-specific sandbox execution."""

    app_id: int = Field(..., description="Target live app identifier.")
    environment: str = Field(
        default="dev",
        description="App environment: dev/test/prod. Use dev for normal authoring.",
    )


class BashSandboxContext(BaseModel):
    """Context for runtime folder binding."""

    app_context: AppContext | None = Field(
        default=None,
        description="App context for binding /app_root to tenant/app workspace.",
    )
    extra_env_vars: dict[str, str] | None = Field(
        default=None,
        description="Extra env vars to inject into sandbox container (方案A). Keys/values plaintext.",
    )


class BashSandboxSchema(BaseModel):
    """Schema for run_bash_script tool."""

    command: str = Field(..., min_length=1, description="Bash command content to execute in sandbox.")
    timeout_seconds: int | None = Field(default=None, ge=1, le=600, description="Execution timeout in seconds.")
    working_dir: str = Field(
        default="/workspace",
        description="Sandbox working directory (/workspace or /app_root when app_context is provided).",
    )
    with_context: BashSandboxContext | None = Field(
        default=None,
        description="Context for runtime folder binding. Supports app_context. DO NOT pass json string, use dictionary/object format when calling the tool from agent code.",
    )

    @field_validator("with_context", mode="before")
    @classmethod
    def parse_with_context(cls, v):
        """Parse with_context from JSON string if needed."""
        if isinstance(v, str):
            try:
                import json

                # Try to parse as JSON first
                parsed = json.loads(v)
                # If it's a dict, let Pydantic validate it as BashSandboxContext
                return parsed
            except (json.JSONDecodeError, ValueError):
                # If it's not valid JSON, return as-is and let Pydantic handle the error
                return v
        return v


def _parse_context_parameter(with_context: BashSandboxContext | str | None) -> BashSandboxContext | None:
    """Parse with_context from JSON string if needed.

    Args:
        with_context: Context parameter (may be JSON string from LLM)

    Returns:
        Parsed BashSandboxContext or None

    Raises:
        SandboxValidationError: If JSON string is invalid
    """
    if isinstance(with_context, str):
        try:
            return BashSandboxContext.model_validate_json(with_context)
        except Exception as e:
            raise SandboxValidationError(
                code="SANDBOX_INVALID_CONTEXT",
                message=f"Invalid with_context format: expected dictionary or JSON object, got string. Error: {e}",
                metadata={"ok": False, "retriable": False},
            )
    return with_context


_DANGEROUS_COMMAND_PATTERNS = [
    re.compile(r"(^|\s)rm\s+-rf\s+/\s*($|\s)"),
    re.compile(r"(^|\s)(shutdown|reboot|poweroff)\b"),
    re.compile(r"(^|\s)mkfs(\.| )"),
]


def _check_dangerous_command(command: str) -> None:
    """Check for dangerous command patterns. Raises on violation."""
    for pattern in _DANGEROUS_COMMAND_PATTERNS:
        if pattern.search(command):
            raise SandboxValidationError(
                code="LIVE_APP_COMMAND_BLOCKED",
                message="Command is blocked by safety policy.",
            )


def _actor_ctx(runtime) -> ActorContext:
    return ActorContext(
        tenant_id=runtime.user.tenant_id,
        user_id=runtime.user.user_id,
        user_role=runtime.user.role,
    )


async def _validate_app_context(runtime, app_id: int, environment: str = "dev") -> str:
    """Validate app context and return app_root_subpath.

    Returns:
        app_root_subpath string for mounting

    Raises:
        SandboxValidationError: If app not found or not accessible
    """
    try:
        async with app_db_session() as db_session:
            service = LiveAppService.create(tenant_id=runtime.user.tenant_id, db_session=db_session)
            await service.get_app_for_actor(app_id=app_id, actor=_actor_ctx(runtime))
    except ResourceNotFoundError:
        raise SandboxValidationError(
            code="LIVE_APP_CONTEXT_VALIDATION_ERROR",
            message="Live app not found",
        )
    except ValidationError as e:
        raise SandboxValidationError(
            code="LIVE_APP_CONTEXT_VALIDATION_ERROR",
            message=e.message,
        )
    except Exception as e:
        logger.exception("Failed to validate app before sandbox command")
        raise SandboxValidationError(
            code="LIVE_APP_CONTEXT_VALIDATION_ERROR",
            message=f"Failed to validate app: {e}",
        )

    # Construct app_root_subpath using the same pattern as get_tenant_live_app_path
    app_root_subpath = f"tenants/tenant_{runtime.user.tenant_id}/apps/app_{app_id}/env/{environment}"
    return app_root_subpath


def _resolve_skill_env_vars(command: str, tenant_id: int, user_id: int) -> dict[str, str]:
    """Parse skill paths from command and resolve env vars via SkillService.

    Scans the command for patterns like /skills-tenant/<name>/ and
    /workspace/skills/<name>/ to detect which skill scripts are being
    invoked, then delegates to SkillService for env var resolution.
    This keeps the bash tool decoupled from filesystem paths and encryption.
    """
    from apps.tenant_app_service.skills.service import SkillService

    result: dict[str, str] = {}
    svc = SkillService()

    # Detect tenant skills: /skills-tenant/<skill_name>/
    for match in re.finditer(r"/skills-tenant/([^/\"'\s]+)", command):
        name = match.group(1)
        try:
            envs = svc.get_decrypted_env_vars(tenant_id, user_id, "tenant", name)
            result.update(envs)
        except Exception as e:
            logger.warning("Failed to resolve env vars for tenant skill '%s': %s", name, e)

    # Detect personal skills: /workspace/skills/<skill_name>/
    for match in re.finditer(r"/workspace/skills/([^/\"'\s]+)", command):
        name = match.group(1)
        try:
            envs = svc.get_decrypted_env_vars(tenant_id, user_id, "personal", name)
            result.update(envs)
        except Exception as e:
            logger.warning("Failed to resolve env vars for personal skill '%s': %s", name, e)

    return result


def _sandbox_error_to_tool_result(e: SandboxError) -> ToolResult:
    """Convert SandboxError to ToolResult."""
    return ToolResult.error_result(
        code=e.code,
        message=e.message,
        retryable=e.retryable,
        metadata=e.metadata,
    )


def _sandbox_result_to_tool_result(
    result: SandboxResult,
    app_root_subpath: str | None,
) -> ToolResult:
    """Convert SandboxResult to ToolResult."""
    # Build execution payload
    payload = {
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "duration_ms": result.duration_ms,
        "output_truncated": result.output_truncated,
        "timed_out": result.timed_out,
    }

    # Add path context for app workspace
    if app_root_subpath is not None:
        payload["workspace_dir"] = "/workspace"
        payload["app_root_dir"] = "/app_root"
        payload["app_root_subpath"] = app_root_subpath

    # Build metadata
    metadata = {
        "ok": result.ok,
        "request_id": result.request_id,
        "command_hash": result.command_hash,
        "status_code": result.status_code,
    }

    # Handle different outcomes
    if result.timed_out:
        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=json.dumps(payload, ensure_ascii=False),
            error=ToolError(
                code="SANDBOX_COMMAND_TIMEOUT",
                message="Command timed out.",
                retryable=True,
            ),
            metadata=metadata,
        )

    if result.exit_code != 0:
        payload["failure_stage"] = result.failure_stage
        # Build error message using shared helper (includes first 5 lines + metadata hint)
        error_msg = _build_non_zero_exit_message(
            result.exit_code,
            {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "failure_stage": result.failure_stage,
            },
        )

        return ToolResult(
            status=ToolResultStatus.ERROR,
            content=json.dumps(payload, ensure_ascii=False),
            error=ToolError(
                code="SANDBOX_COMMAND_FAILED",
                message=error_msg,
                retryable=False,
            ),
            metadata=metadata,
        )

    # Success
    return ToolResult.success(payload, metadata=metadata)


@tool(args_schema=BashSandboxSchema)
async def run_bash_script(
    command: str,
    timeout_seconds: int | None = None,
    working_dir: str = "/workspace",
    with_context: BashSandboxContext | None = None,
    config: RunnableConfig = None,
) -> ToolResult:
    """Run a bash command in a controlled sandbox controller service.

    Runtime capabilities are intentionally minimal and image-dependent.
    In the default sandbox runner image, available tools include:
    `bash`, coreutils, Python 3, `git`, `node`, and `npm`.

    Skill scripts are available at scope-specific paths inside the sandbox:
    - Builtin skills: `/skills/<skill_name>/`
    - Tenant skills: `/skills-tenant/<skill_name>/`
    - Personal skills: `/workspace/skills/<skill_name>/`

    To run a skill script, cd into the skill directory first so relative paths work:
    `cd /skills/<skill_name> && python scripts/<script.py> [args]`
    (Use the exact path returned by `load_skill` for tenant/personal skills.)

    DO NOT run any skill script without calling `load_skill(skill_name=...)` first.
    Running skill scripts without loading the skill bypasses the skill lifecycle and is not allowed.

    Important: For live app operations, always prefer the dedicated skill tools (read_app_file,
    write_app_file, list_app_files, grep_app_files, etc.). Only fall back to this tool when no
    dedicated tool covers the task.

    Context-aware execution:
    - When with_context contains app_context: {app_id, environment}, validates app exists,
      applies safety checks, and automatically binds /app_root to the app workspace.
    - Dangerous command patterns are blocked in app context mode.
    """
    try:
        # Extract runtime context
        runtime = extract_runtime_context(config)

        # Parse context parameter (handle JSON string from LLM)
        parsed_context = _parse_context_parameter(with_context)

        # Determine execution parameters
        final_working_dir = working_dir
        app_root_subpath: str | None = None

        # Handle app context
        if parsed_context and parsed_context.app_context:
            app_ctx = parsed_context.app_context

            # Check for dangerous commands (required for app workspace)
            _check_dangerous_command(command)

            # Validate app exists and get mount path
            app_root_subpath = await _validate_app_context(runtime, app_ctx.app_id, app_ctx.environment)
            final_working_dir = "/app_root"

        # Build execution context for client (identity/tracing only)
        execution_context = SandboxExecutionContext(
            tenant_id=runtime.user.tenant_id,
            user_id=runtime.user.user_id,
            thread_id=runtime.thread_id,
            session_id=runtime.session_id,
            agent_id=runtime.agent_id,
            tool_name="run_bash_script",
        )

        # Resolve env vars from skill config.json (auto-detect from command paths)
        auto_env_vars = _resolve_skill_env_vars(command, runtime.user.tenant_id, runtime.user.user_id)

        # Merge with manually provided env vars (manual takes precedence)
        extra_env_vars = dict(auto_env_vars)
        if parsed_context and parsed_context.extra_env_vars:
            extra_env_vars.update(parsed_context.extra_env_vars)
        extra_env_vars = extra_env_vars or None

        # Execute via shared client
        client = SandboxClient()
        try:
            sandbox_result = await client.execute(
                command=command,
                timeout_seconds=timeout_seconds or 30,
                context=execution_context,
                working_dir=final_working_dir,
                app_root_subpath=app_root_subpath,
                extra_env_vars=extra_env_vars,
            )
        finally:
            await client.close()

        # Convert to ToolResult
        return _sandbox_result_to_tool_result(sandbox_result, app_root_subpath)

    except SandboxError as e:
        # Convert domain exceptions to ToolResult
        return _sandbox_error_to_tool_result(e)
