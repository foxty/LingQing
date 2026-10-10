"""Shared sandbox execution client.

Provides unified sandbox controller communication for both agent tools
and scheduled task execution.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import aiohttp

from apps.config import EnvConfig
from apps.shared.sandbox.schemas import (
    SandboxExecuteRequest,
    SandboxExecuteRequestContext,
    SandboxExecuteResponse,
)
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


def _sandbox_controller_headers() -> dict[str, str]:
    token = EnvConfig.SANDBOX_CONTROLLER_API_TOKEN
    if not token:
        return {}
    return {"X-Sandbox-Token": token}


@dataclass
class SandboxExecutionContext:
    """Caller identity and tracing context for sandbox operations.

    Contains only who is calling (tenant, user, agent/task IDs) and tracing
    fields. Mount configuration (app_root_subpath, working_dir) is passed
    explicitly to execute() — keeping this struct free of runtime mount state.
    """

    tenant_id: int
    user_id: int
    # Optional - for agent tool execution
    thread_id: str | None = None
    session_id: str | None = None
    agent_id: int | None = None
    tool_name: str | None = None
    # Optional - for scheduled task execution
    task_id: int | None = None

    def to_request_context(
        self,
        *,
        command_hash: str,
        app_root_subpath: str | None = None,
        extra_env_vars: dict[str, str] | None = None,
    ) -> SandboxExecuteRequestContext:
        """Convert to schema for sandbox controller request.

        Args:
            command_hash: SHA-256 hash of the command (computed by client).
            app_root_subpath: Relative path to mount as /app_root (pass-through).
            extra_env_vars: Extra env vars to inject into sandbox container (方案A).
        """
        return SandboxExecuteRequestContext(
            tenant_id=self.tenant_id,
            user_id=self.user_id,
            thread_id=self.thread_id or "",
            session_id=self.session_id or "",
            agent_id=self.agent_id or 0,
            tool_name=self.tool_name or "bash",
            command_hash=command_hash,
            app_root_subpath=app_root_subpath,
            extra_env_vars=extra_env_vars,
        )


@dataclass
class SandboxResult:
    """Unified sandbox execution result."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int | None = None
    output_truncated: bool = False
    timed_out: bool = False
    failure_stage: str | None = None
    # Raw response data
    ok: bool = True
    request_id: str | None = None
    status_code: int | None = None
    command_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for compatibility with existing code."""
        return {
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
            "output_truncated": self.output_truncated,
            "timed_out": self.timed_out,
            "failure_stage": self.failure_stage,
            "ok": self.ok,
            "request_id": self.request_id,
            "status_code": self.status_code,
            "command_hash": self.command_hash,
        }

    @property
    def is_success(self) -> bool:
        """Check if execution was successful."""
        return self.ok and self.exit_code == 0 and not self.timed_out


class SandboxError(Exception):
    """Base exception for sandbox operations."""

    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        metadata: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.retryable = retryable
        self.metadata = metadata or {}
        super().__init__(message)


class SandboxValidationError(SandboxError):
    """Validation errors (non-retryable)."""

    def __init__(self, code: str, message: str, metadata: dict[str, Any] | None = None):
        super().__init__(code, message, retryable=False, metadata=metadata)


class SandboxHttpError(SandboxError):
    """HTTP/infrastructure errors (may be retryable)."""

    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        metadata: dict[str, Any] | None = None,
    ):
        super().__init__(code, message, retryable=retryable, metadata=metadata)


def _hash_command(command: str) -> str:
    """Compute short hash of command for logging/tracing."""
    return hashlib.sha256(command.encode("utf-8")).hexdigest()[:16]


def _truncate_for_log(value: Any, *, max_chars: int = 400) -> str:
    """Truncate value for logging."""
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def _summarize_output_for_error(result: dict[str, Any], *, max_lines: int = 20, max_chars: int = 1_000) -> str:
    """Extract first N lines of output for error messages.

    Returns a truncated but more useful error summary than just the first line.
    Full output is always available in result["stdout"] / result["stderr"].
    """
    stderr = str(result.get("stderr", "")).strip()
    stdout = str(result.get("stdout", "")).strip()
    source = stderr or stdout
    if not source:
        return ""
    lines = source.splitlines()
    summary_lines = lines[:max_lines]
    summary = "\n".join(summary_lines)
    if len(summary) > max_chars:
        summary = f"{summary[:max_chars]}..."
    if len(lines) > max_lines:
        summary = f"{summary}\n... ({len(lines) - max_lines} more lines)"
    return summary


def _build_non_zero_exit_message(exit_code: int, result: dict[str, Any]) -> str:
    """Build user-friendly message for non-zero exit.

    Includes first few lines of output for quick diagnosis.
    Full stdout/stderr is available in SandboxError.metadata.
    """
    failure_stage = result.get("failure_stage")
    details = _summarize_output_for_error(result)
    if exit_code == 125 or failure_stage == "container_start":
        message = (
            "Sandbox runner failed to start (exit 125). Check sandbox-controller logs for image/mount/network issues."
        )
    else:
        message = f"Command exited with non-zero code: {exit_code}."
    if details:
        message = f"{message}\n\nOutput (first 5 lines):\n{details}"
    else:
        message = f"{message}\n\nNo output captured (stdout and stderr are empty)."
    message += "\n\nFull stdout/stderr available in exception metadata."
    return message


class SandboxClient:
    """Shared sandbox execution client.

    Provides unified sandbox controller communication with consistent:
    - Request validation and building
    - HTTP transport
    - Response parsing
    - Error handling
    - Result composition

    Usage:
        client = SandboxClient()
        result = await client.execute(
            command="python jobs/sync_prs.py",
            timeout_seconds=300,
            context=SandboxExecutionContext(
                tenant_id=1,
                user_id=1,
                task_id=42,
            ),
            working_dir="/app_root",
            app_root_subpath="tenants/tenant_1/apps/app_5/env/prod",
        )
    """

    def __init__(self, *, base_url: str | None = None, http_client: aiohttp.ClientSession | None = None):
        """Initialize sandbox client.

        Args:
            base_url: Override sandbox controller URL (defaults to EnvConfig).
            http_client: Optional existing HTTP client (for testing).
        """
        self._base_url = base_url or EnvConfig.AGENT_SANDBOX_BASE_URL
        self._client = http_client
        self._owns_client = http_client is None

    async def _get_client(self, timeout: aiohttp.ClientTimeout) -> aiohttp.ClientSession:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = aiohttp.ClientSession(timeout=timeout)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._client and self._owns_client:
            await self._client.close()
            self._client = None

    async def __aenter__(self) -> SandboxClient:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def _build_request(
        self,
        command: str,
        timeout_seconds: int,
        context: SandboxExecutionContext,
        working_dir: str = "/workspace",
        app_root_subpath: str | None = None,
        extra_env_vars: dict[str, str] | None = None,
    ) -> tuple[dict, str, aiohttp.ClientTimeout, str]:
        """Build sandbox controller request payload.

        Returns:
            Tuple of (request_payload, controller_url, controller_timeout, command_hash)
        """
        command_hash = _hash_command(command)

        request_payload = SandboxExecuteRequest(
            command=command,
            timeout_seconds=timeout_seconds,
            working_dir=working_dir,
            output_max_bytes=EnvConfig.AGENT_SANDBOX_OUTPUT_MAX_BYTES,
            request_context=context.to_request_context(
                command_hash=command_hash,
                app_root_subpath=app_root_subpath,
                extra_env_vars=extra_env_vars,
            ),
        )

        controller_url = f"{self._base_url.rstrip('/')}/execute/bash"
        controller_timeout = aiohttp.ClientTimeout(
            total=timeout_seconds + EnvConfig.AGENT_SANDBOX_CLIENT_TIMEOUT_BUFFER_SECONDS
        )

        return request_payload.model_dump(), controller_url, controller_timeout, command_hash

    async def _execute_request(
        self,
        request_payload: dict,
        controller_url: str,
        controller_timeout: aiohttp.ClientTimeout,
        command_hash: str,
        resolved_timeout: int,
        working_dir: str,
        app_root_subpath: str | None,
        context: SandboxExecutionContext,
    ) -> tuple[int, dict]:
        """Execute HTTP request to sandbox controller.

        Returns:
            Tuple of (http_status, response_payload)

        Raises:
            SandboxHttpError: On timeout, network errors, or HTTP errors
        """
        client = await self._get_client(controller_timeout)

        try:
            async with client.post(
                url=controller_url,
                json=request_payload,
                headers=_sandbox_controller_headers(),
            ) as response:
                raw_text = await response.text()
                try:
                    payload = json.loads(raw_text) if raw_text else {}
                except json.JSONDecodeError:
                    logger.error(
                        "Sandbox controller returned invalid JSON: tenant=%s user=%s command_hash=%s "
                        "status=%s url=%s body_snippet=%s",
                        context.tenant_id,
                        context.user_id,
                        command_hash,
                        response.status,
                        controller_url,
                        _truncate_for_log(raw_text),
                    )
                    payload = {
                        "ok": False,
                        "error": {"message": "Invalid JSON from sandbox controller service"},
                        "raw": raw_text,
                    }

                if response.status >= 500:
                    logger.error(
                        "Sandbox controller server error: tenant=%s user=%s command_hash=%s "
                        "status=%s timeout_seconds=%s working_dir=%s app_root_subpath=%s "
                        "error_message=%s raw_snippet=%s",
                        context.tenant_id,
                        context.user_id,
                        command_hash,
                        response.status,
                        resolved_timeout,
                        working_dir,
                        app_root_subpath,
                        payload.get("error", {}).get("message"),
                        _truncate_for_log(payload),
                    )
                    raise SandboxHttpError(
                        code="SANDBOX_SIDECAR_UNAVAILABLE",
                        message="Sandbox controller service returned server error.",
                        retryable=True,
                        metadata={"ok": False, "status_code": response.status, "raw_result": payload},
                    )

                if response.status >= 400:
                    logger.warning(
                        "Sandbox controller rejected request: tenant=%s user=%s command_hash=%s "
                        "status=%s timeout_seconds=%s working_dir=%s app_root_subpath=%s "
                        "error_message=%s raw_snippet=%s",
                        context.tenant_id,
                        context.user_id,
                        command_hash,
                        response.status,
                        resolved_timeout,
                        working_dir,
                        app_root_subpath,
                        payload.get("error", {}).get("message"),
                        _truncate_for_log(payload),
                    )
                    raise SandboxHttpError(
                        code="SANDBOX_REQUEST_REJECTED",
                        message=payload.get("error", {}).get("message", "Sandbox request rejected."),
                        metadata={"ok": False, "status_code": response.status, "raw_result": payload},
                    )

                return response.status, payload

        except TimeoutError:
            logger.error(
                "Sandbox controller request timed out: tenant=%s user=%s command_hash=%s "
                "timeout_seconds=%s controller_timeout_total=%s url=%s working_dir=%s app_root_subpath=%s",
                context.tenant_id,
                context.user_id,
                command_hash,
                resolved_timeout,
                controller_timeout.total,
                controller_url,
                working_dir,
                app_root_subpath,
            )
            raise SandboxHttpError(
                code="SANDBOX_SIDECAR_TIMEOUT",
                message="Sandbox controller request timed out.",
                retryable=True,
                metadata={"ok": False},
            )
        except SandboxHttpError:
            raise
        except Exception as e:
            logger.exception(
                "Sandbox controller call failed: tenant=%s user=%s command_hash=%s "
                "url=%s timeout_seconds=%s working_dir=%s app_root_subpath=%s error_type=%s",
                context.tenant_id,
                context.user_id,
                command_hash,
                controller_url,
                resolved_timeout,
                working_dir,
                app_root_subpath,
                type(e).__name__,
            )
            raise SandboxHttpError(
                code="SANDBOX_SIDECAR_ERROR",
                message=str(e),
                retryable=True,
                metadata={"ok": False},
            )

    def _parse_response(
        self,
        http_status: int,
        payload: dict,
        command_hash: str,
        app_root_subpath: str | None,
    ) -> SandboxResult:
        """Parse sandbox controller response into unified result.

        Uses SandboxExecuteResponse DTO for type-safe parsing.
        """
        # Parse using shared DTO for type safety and validation
        response = SandboxExecuteResponse.model_validate(payload)
        result_data = response.result

        return SandboxResult(
            exit_code=result_data.exit_code,
            stdout=result_data.stdout,
            stderr=result_data.stderr,
            duration_ms=result_data.duration_ms,
            output_truncated=result_data.output_truncated,
            timed_out=result_data.timed_out,
            failure_stage=result_data.failure_stage,
            ok=response.ok,
            request_id=response.request_id,
            status_code=http_status,
            command_hash=command_hash,
        )

    async def execute(
        self,
        command: str,
        timeout_seconds: int,
        context: SandboxExecutionContext,
        working_dir: str = "/workspace",
        app_root_subpath: str | None = None,
        extra_env_vars: dict[str, str] | None = None,
    ) -> SandboxResult:
        """Execute command in sandbox with full context.

        This is the main entry point for sandbox execution. It handles:
        - Request building and validation
        - HTTP transport to sandbox controller
        - Response parsing
        - Error handling

        Args:
            command: Bash command to execute
            timeout_seconds: Execution timeout (max 600s)
            context: Execution context with tenant/user info
            working_dir: Working directory (/workspace or /app_root)
            app_root_subpath: Override app workspace subpath
            extra_env_vars: Extra env vars to inject into sandbox container (方案A)

        Returns:
            SandboxResult with execution outcome

        Raises:
            SandboxValidationError: If inputs are invalid
            SandboxHttpError: On HTTP/transport errors
        """
        # Validate inputs
        command = command.strip()
        if not command:
            raise SandboxValidationError(
                code="SANDBOX_EMPTY_COMMAND",
                message="Command must not be empty.",
                metadata={"ok": False, "retriable": False},
            )

        if len(command) > EnvConfig.AGENT_SANDBOX_MAX_COMMAND_CHARS:
            raise SandboxValidationError(
                code="SANDBOX_COMMAND_TOO_LONG",
                message=(
                    f"Command length exceeds limit ({EnvConfig.AGENT_SANDBOX_MAX_COMMAND_CHARS} chars). "
                    "Split command into smaller steps."
                ),
                metadata={"ok": False, "retriable": False},
            )

        # Apply defaults and validate timeout
        default_timeout = timeout_seconds or EnvConfig.AGENT_SANDBOX_DEFAULT_TIMEOUT_SECONDS
        if default_timeout > EnvConfig.AGENT_SANDBOX_MAX_TIMEOUT_SECONDS:
            raise SandboxValidationError(
                code="SANDBOX_TIMEOUT_TOO_LARGE",
                message=f"timeout_seconds={default_timeout} exceeds max {EnvConfig.AGENT_SANDBOX_MAX_TIMEOUT_SECONDS}.",
                metadata={"ok": False, "retriable": False},
            )
        resolved_timeout = default_timeout

        # Validate working_dir/app_root_subpath consistency
        if working_dir == "/app_root" and not app_root_subpath:
            raise SandboxValidationError(
                code="SANDBOX_INVALID_WORKDIR",
                message="working_dir '/app_root' requires app_root_subpath.",
                metadata={"ok": False, "retriable": False},
            )

        # Build request
        request_payload, controller_url, controller_timeout, command_hash = self._build_request(
            command=command,
            timeout_seconds=resolved_timeout,
            context=context,
            working_dir=working_dir,
            app_root_subpath=app_root_subpath,
            extra_env_vars=extra_env_vars,
        )

        # Execute request
        http_status, payload = await self._execute_request(
            request_payload=request_payload,
            controller_url=controller_url,
            controller_timeout=controller_timeout,
            command_hash=command_hash,
            resolved_timeout=resolved_timeout,
            working_dir=working_dir,
            app_root_subpath=app_root_subpath,
            context=context,
        )

        # Parse response
        result = self._parse_response(http_status, payload, command_hash, app_root_subpath)

        logger.info(
            "Sandbox execution finished: tenant=%s user=%s command_hash=%s exit_code=%s timed_out=%s",
            context.tenant_id,
            context.user_id,
            command_hash,
            result.exit_code,
            result.timed_out,
        )

        return result

    def raise_on_error(self, result: SandboxResult) -> None:
        """Raise appropriate exception for failed sandbox execution.

        Args:
            result: SandboxResult from execute()

        Raises:
            SandboxHttpError: For transport/timeouts
            SandboxError: For non-zero exit code
        """
        if result.timed_out:
            # Build detailed timeout message with stderr output
            timeout_msg = f"Command timed out after {result.duration_ms or 'unknown'}ms."
            if result.stderr:
                timeout_msg += f"\n\nStderr output:\n{result.stderr}"
            timeout_msg += "\n\nFull stdout/stderr available in exception metadata."

            raise SandboxError(
                code="SANDBOX_COMMAND_TIMEOUT",
                message=timeout_msg,
                retryable=True,
                metadata=result.to_dict(),
            )

        if result.exit_code != 0:
            # Build metadata with full output for diagnosis
            error_metadata = result.to_dict()

            error_message = _build_non_zero_exit_message(
                result.exit_code,
                {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "failure_stage": result.failure_stage,
                },
            )
            raise SandboxError(
                code="SANDBOX_COMMAND_FAILED",
                message=error_message,
                retryable=False,
                metadata=error_metadata,
            )

    @staticmethod
    def write_output_to_workspace(
        result: SandboxResult,
        workspace_dir: str,
        *,
        stdout_file: str = "sandbox_stdout.log",
        stderr_file: str = "sandbox_stderr.log",
    ) -> tuple[str, str]:
        """Write full stdout/stderr to workspace files for LLM diagnosis.

        Use this when sandbox execution fails and you want to preserve the
        full output for the LLM to analyze in subsequent tool calls.

        Args:
            result: SandboxResult from execute()
            workspace_dir: Directory to write output files (e.g., thread workspace)
            stdout_file: Filename for stdout (default: sandbox_stdout.log)
            stderr_file: Filename for stderr (default: sandbox_stderr.log)

        Returns:
            Tuple of (stdout_path, stderr_path) — paths to written files

        Example:
            try:
                result = await client.execute(...)
                client.raise_on_error(result)
            except SandboxError as e:
                stdout_path, stderr_path = client.write_output_to_workspace(
                    result=e.metadata,  # or the original SandboxResult
                    workspace_dir="/path/to/workspace",
                )
                # LLM can now read these files for full context
        """
        import os

        os.makedirs(workspace_dir, exist_ok=True)

        stdout_path = os.path.join(workspace_dir, stdout_file)
        stderr_path = os.path.join(workspace_dir, stderr_file)

        # Convert result to dict if it's a SandboxResult dataclass
        if hasattr(result, "to_dict"):
            data = result.to_dict()
        else:
            data = result

        with open(stdout_path, "w", encoding="utf-8") as f:
            f.write(data.get("stdout", ""))

        with open(stderr_path, "w", encoding="utf-8") as f:
            f.write(data.get("stderr", ""))

        logger.info(
            "Wrote sandbox output to workspace: stdout=%s (%d bytes), stderr=%s (%d bytes)",
            stdout_path,
            len(data.get("stdout", "")),
            stderr_path,
            len(data.get("stderr", "")),
        )

        return stdout_path, stderr_path
