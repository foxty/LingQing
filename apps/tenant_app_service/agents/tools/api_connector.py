"""Agent tools for API connector inspection and invocation."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.api_connector.schemas import ApiOperationCallParameters
from apps.shared.external_systems.application.wiring import api_connector_execution_service
from apps.tenant_app_service.agents.context import extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

# Cap serialized tool body size; shrink by structure (not byte slicing) when over budget.
RESPONSE_BODY_MAX_CHARS = 6000

# Shape once: cap list length and string size. Budget fitting is list-halving afterward.
RESPONSE_SHAPE_MAX_ITEMS = 20
RESPONSE_SHAPE_MAX_STRING_CHARS = 1000

_TRUNCATION_HINT = (
    "Response truncated structurally while keeping valid JSON. "
    "Retry with a smaller count/limit/pageSize or a narrower query; do not repeat the same page size."
)

_SHAPE_OPTIONS = {
    "max_items": RESPONSE_SHAPE_MAX_ITEMS,
    "max_string_chars": RESPONSE_SHAPE_MAX_STRING_CHARS,
}


def _truncate_string(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    truncated_chars = len(value) - max_chars
    return f"{value[:max_chars]}... [truncated {truncated_chars} chars]"


def _shape_response_value(
    value,
    *,
    max_items: int,
    max_string_chars: int,
):
    if isinstance(value, str):
        return _truncate_string(value, max_string_chars)

    if isinstance(value, list):
        return [
            _shape_response_value(item, max_items=max_items, max_string_chars=max_string_chars)
            for item in value[:max_items]
        ]

    if isinstance(value, dict):
        return {
            key: _shape_response_value(item, max_items=max_items, max_string_chars=max_string_chars)
            for key, item in value.items()
        }

    return value


def _to_response_text(body) -> str:
    if isinstance(body, str):
        return body
    try:
        return json.dumps(body, ensure_ascii=False, default=str)
    except Exception:
        return str(body)


def _halve_largest_list(value: Any) -> tuple[Any, bool]:
    """Cut the longest list in half (keep the prefix). Returns (value, changed)."""
    if isinstance(value, list):
        if len(value) <= 1:
            # Recurse into the single item if present; otherwise nothing to cut here.
            if not value:
                return value, False
            item, changed = _halve_largest_list(value[0])
            return [item], changed
        keep = max(1, len(value) // 2)
        return value[:keep], True

    if isinstance(value, dict):
        # Prefer shrinking the longest nested list; fall back to first successful child.
        list_keys = [(key, child) for key, child in value.items() if isinstance(child, list) and len(child) > 1]
        if list_keys:
            key, child = max(list_keys, key=lambda pair: len(pair[1]))
            keep = max(1, len(child) // 2)
            return {**value, key: child[:keep]}, True
        for key, child in value.items():
            shrunk, changed = _halve_largest_list(child)
            if changed:
                return {**value, key: shrunk}, True
        return value, False

    return value, False


def _compact_api_body_for_agent(
    body: Any,
    *,
    max_chars: int = RESPONSE_BODY_MAX_CHARS,
) -> tuple[Any, dict[str, Any]]:
    """Shape once, then shrink lists until serialized size fits ``max_chars``.

    Always returns a JSON-serializable object (never mid-string chunks).
    """
    original_chars = len(_to_response_text(body))
    compacted = _shape_response_value(body, **_SHAPE_OPTIONS)
    truncated = False

    while len(_to_response_text(compacted)) > max_chars:
        compacted, changed = _halve_largest_list(compacted)
        truncated = True
        if not changed:
            break

    size = len(_to_response_text(compacted))
    meta: dict[str, Any] = {
        "body_shaped": True,
        "body_shape_options": dict(_SHAPE_OPTIONS),
        "body_total_chars": original_chars,
        "body_returned_chars": size,
        "body_truncated": truncated,
    }
    if truncated:
        meta["truncation_hint"] = _TRUNCATION_HINT
    return compacted, meta


def _runtime_actor(config: RunnableConfig):
    runtime = extract_runtime_context(config)
    actor = ActorContext(
        tenant_id=runtime.user.tenant_id,
        user_id=runtime.user.user_id,
        user_role=runtime.user.role,
    )
    allowed_ids = runtime.capability_profile.allowed_api_connector_ids if runtime.capability_profile else None
    return runtime, actor, allowed_ids


class GetApiConnectorInfoInput(BaseModel):
    connector_id: int = Field(..., description="Internal connector ID from a search_apis result")


class GetApiOperationDetailInput(BaseModel):
    operation_id: int = Field(..., description="Internal operation ID from a search_apis result")


class CallExternalApiInput(BaseModel):
    operation_id: int = Field(..., description="Internal operation ID from a search_apis result")
    parameters: ApiOperationCallParameters = Field(
        default_factory=ApiOperationCallParameters,
        description="Path/query/header/body parameters for the operation call",
    )


@tool(args_schema=GetApiConnectorInfoInput)
async def get_api_connector_info(
    connector_id: int,
    config: RunnableConfig,
) -> ToolResult:
    """Fetch connector-level description, connection status, and agent instructions once.

    Call this once per connector after ``search_apis`` when provider guidance is needed.
    Do not request connector instructions for every operation.
    """
    try:
        runtime, actor, allowed_ids = _runtime_actor(config)
    except ValueError as exc:
        return ToolResult.error_result(str(exc), code="API_CONNECTOR_INVALID_CONTEXT")

    if allowed_ids is not None and connector_id not in allowed_ids:
        return ToolResult.error_result("Access denied to API connector", code="API_CONNECTOR_FORBIDDEN")

    async with app_db_session() as session:
        from apps.shared.external_systems.api_connector.service import ApiConnectorService

        service = ApiConnectorService(tenant_id=runtime.user.tenant_id, db_session=session)
        connector = await service.get_connector_for_actor(connector_id=connector_id, actor=actor)
        return ToolResult.success(
            {
                "connector_id": connector.id,
                "connector_name": connector.name,
                "description": connector.description,
                "base_url": connector.base_url,
                "credential_mode": connector.credential_mode,
                "connection_status": connector.user_connection_status,
                "agent_instructions": connector.agent_instructions,
            }
        )


@tool(args_schema=GetApiOperationDetailInput)
async def get_api_operation_detail(
    operation_id: int,
    config: RunnableConfig,
) -> ToolResult:
    """Fetch one API operation's metadata and request/response schemas.

    Use after ``search_apis`` when the operation contract is unclear. For connector-level
    guidance, call ``get_api_connector_info`` once instead.
    """
    try:
        runtime, actor, allowed_ids = _runtime_actor(config)
    except ValueError as exc:
        return ToolResult.error_result(str(exc), code="API_CONNECTOR_INVALID_CONTEXT")

    async with app_db_session() as session:
        from apps.shared.external_systems.api_connector.service import ApiConnectorService

        service = ApiConnectorService(tenant_id=runtime.user.tenant_id, db_session=session)
        row, connector = await service.get_operation_by_id_for_actor(
            operation_id=operation_id,
            actor=actor,
        )
        if allowed_ids is not None and connector.id not in allowed_ids:
            return ToolResult.error_result("Access denied to API operation", code="API_CONNECTOR_FORBIDDEN")
        return ToolResult.success(
            {
                "operation_id": row.id,
                "operation_uid": row.operation_uid,
                "connector_id": connector.id,
                "connector_name": connector.name,
                "connector_base_url": connector.base_url,
                "method": row.method,
                "path": row.path_template,
                "summary": row.summary,
                "request_schema": row.request_schema,
                "response_schema": row.response_schema,
            }
        )


@tool(args_schema=CallExternalApiInput)
async def call_external_api(
    operation_id: int,
    config: RunnableConfig,
    parameters: ApiOperationCallParameters | None = None,
) -> ToolResult:
    """Execute one external API operation with runtime parameters.

    Prefer upstream filtering/pagination in ``parameters.query`` such as ``fields``,
    ``count``, ``limit``, ``maxResults``, ``pageSize``, or reduced ``expand`` when supported.
    Large bodies are shaped into valid JSON under a size budget (status ``partial`` when
    truncated). If ``body_truncated`` is true, reduce page size instead of retrying the same call.
    """
    try:
        runtime, actor, allowed_ids = _runtime_actor(config)
    except ValueError as exc:
        return ToolResult.error_result(str(exc), code="API_CONNECTOR_INVALID_CONTEXT")

    async with app_db_session() as session:
        if allowed_ids is not None:
            from apps.shared.external_systems.api_connector.service import ApiConnectorService

            service = ApiConnectorService(tenant_id=runtime.user.tenant_id, db_session=session)
            _row, connector = await service.get_operation_by_id_for_actor(
                operation_id=operation_id,
                actor=actor,
            )
            if connector.id not in allowed_ids:
                return ToolResult.error_result("Access denied to API operation", code="API_CONNECTOR_FORBIDDEN")

        exec_service = api_connector_execution_service(runtime.user.tenant_id, session)
        result = await exec_service.execute_operation_by_id_for_actor(
            operation_id=operation_id,
            actor=actor,
            parameters=parameters or ApiOperationCallParameters(),
        )
        if result.error:
            return ToolResult.error_result(
                result.error,
                code="API_CONNECTOR_CALL_FAILED",
                metadata={
                    "status_code": result.status_code,
                    "elapsed_ms": result.elapsed_ms,
                },
            )
        compacted_body, body_meta = _compact_api_body_for_agent(result.body)
        payload = {
            "status_code": result.status_code,
            "body": compacted_body,
            **body_meta,
        }
        metadata = {"elapsed_ms": result.elapsed_ms}
        if body_meta.get("body_truncated"):
            return ToolResult.partial(payload, metadata=metadata)
        return ToolResult.success(payload, metadata=metadata)
