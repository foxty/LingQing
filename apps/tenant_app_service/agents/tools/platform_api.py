"""Tool for executing platform REST API calls."""

import json
import os
from typing import Any

import aiohttp
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)


class PlatformApiCallSchema(BaseModel):
    """Schema for call_platform_api tool."""

    method: str = Field(..., description="HTTP method (GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS).")
    path: str = Field(..., description="Raw request path, e.g. /data-sources/1/query.")
    path_params: dict[str, Any] = Field(default_factory=dict, description="Path parameter values.")
    query_params: dict[str, Any] = Field(default_factory=dict, description="Query parameter values.")
    body: dict[str, Any] | None = Field(default=None, description="JSON request body.")
    timeout_seconds: int = Field(default=30, ge=1, le=120, description="Request timeout in seconds.")


def _render_path(path_template: str, path_params: dict[str, Any]) -> str:
    """Substitute {param} placeholders in path template."""
    rendered = path_template
    for key, value in path_params.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def _get_base_url() -> str:
    """Get internal API base URL for platform calls."""
    return os.getenv("AGENT_PLATFORM_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


@tool(args_schema=PlatformApiCallSchema)
async def call_platform_api(
    method: str,
    path: str,
    path_params: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timeout_seconds: int = 30,
    config: RunnableConfig = None,
) -> ToolResult:
    """Execute a platform REST API call.

    Uses generic REST input via ``method`` + ``path``.
    """
    operation_id: str | None = None
    operation_key: str | None = None
    resolved_method = method.upper()
    path_template = path

    if resolved_method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        return ToolResult.error_result(
            code="PLATFORM_API_INVALID_METHOD",
            message=f"Invalid HTTP method: {resolved_method}",
            metadata={
                "ok": False,
                "status_code": 400,
                "retriable": False,
                "operation_id": operation_id,
                "operation_key": operation_key,
            },
        )

    try:
        runtime = extract_runtime_context(config)
    except ValueError as e:
        return ToolResult.error_result(
            code="PLATFORM_API_INVALID_CONTEXT",
            message=str(e),
            metadata={
                "ok": False,
                "status_code": 400,
                "retriable": False,
                "operation_id": operation_id,
                "operation_key": operation_key,
            },
        )

    token = getattr(runtime.user, "access_token", None)

    if not token:
        return ToolResult.error_result(
            code="PLATFORM_API_MISSING_TOKEN",
            message=(
                "JWT token is not available in agent runtime context. "
                "Enable token forwarding before using call_platform_api."
            ),
            metadata={
                "ok": False,
                "status_code": 401,
                "retriable": False,
                "operation_id": operation_id,
                "operation_key": operation_key,
            },
        )

    if not path_template.startswith("/"):
        return ToolResult.error_result(
            code="PLATFORM_API_INVALID_PATH",
            message=f"Invalid path: {path_template}",
            metadata={
                "ok": False,
                "status_code": 400,
                "retriable": False,
                "operation_id": operation_id,
            },
        )

    final_path = _render_path(path_template, path_params or {})
    if "{" in final_path or "}" in final_path:
        return ToolResult.error_result(
            code="PLATFORM_API_MISSING_PATH_PARAMS",
            message="Missing required path parameters",
            metadata={
                "ok": False,
                "status_code": 400,
                "missing_fields": ["path.<template-parameter>"],
                "operation_id": operation_id,
                "operation_key": operation_key,
                "retriable": False,
            },
        )

    url = f"{_get_base_url()}{final_path}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Agent-Request": "true",
        "X-Agent-Thread-Id": runtime.thread_id,
        "X-Agent-Session-Id": runtime.session_id,
        "X-Agent-Id": str(runtime.agent_id),
        "X-Agent-Name": runtime.agent_name,
    }

    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method=resolved_method,
                url=url,
                params=query_params or None,
                json=body,
                headers=headers,
            ) as response:
                raw_text = await response.text()
                try:
                    payload = json.loads(raw_text) if raw_text else None
                except json.JSONDecodeError:
                    payload = {"raw": raw_text}

                ok = 200 <= response.status < 300
                retriable = response.status in {408, 429, 500, 502, 503, 504}

                result = {
                    "ok": ok,
                    "status_code": response.status,
                    "operation_id": operation_id,
                    "operation_key": operation_key,
                    "method": resolved_method,
                    "path": final_path,
                    "retriable": retriable,
                }
                if ok:
                    result["data"] = payload
                else:
                    result["error"] = payload

                if ok:
                    return ToolResult.success(result)
                return ToolResult.error_result(
                    code="PLATFORM_API_REQUEST_FAILED",
                    message=f"Platform API request failed with status {response.status}",
                    metadata=result,
                )

    except TimeoutError:
        return ToolResult.error_result(
            code="PLATFORM_API_TIMEOUT",
            message="Request timeout",
            metadata={
                "ok": False,
                "status_code": 408,
                "operation_id": operation_id,
                "operation_key": operation_key,
                "retriable": True,
            },
        )
    except Exception as e:
        logger.exception("Platform API call failed: %s", operation_id)
        return ToolResult.error_result(
            code="PLATFORM_API_INTERNAL_ERROR",
            message=str(e),
            metadata={
                "ok": False,
                "status_code": 500,
                "operation_id": operation_id,
                "operation_key": operation_key,
                "retriable": True,
            },
        )
