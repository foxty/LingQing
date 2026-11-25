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

# Final payload chunking guardrail: split oversized response text into fixed-size chunks.
RESPONSE_BODY_CHUNK_SIZE = 2000
# Return at most this many chunks to cap final tool output size.
RESPONSE_BODY_MAX_CHUNKS = 3

# Structure shaping guardrails: trim nested JSON before chunking to avoid huge trees.
RESPONSE_SHAPE_MAX_DEPTH = 4
RESPONSE_SHAPE_MAX_ITEMS = 20
RESPONSE_SHAPE_MAX_OBJECT_KEYS = 40
RESPONSE_SHAPE_MAX_STRING_CHARS = 1000


def _truncate_string(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    truncated_chars = len(value) - max_chars
    return f"{value[:max_chars]}... [truncated {truncated_chars} chars]"


def _shape_response_value(
    value,
    *,
    depth: int,
    max_depth: int,
    max_items: int,
    max_object_keys: int,
    max_string_chars: int,
):
    if isinstance(value, str):
        return _truncate_string(value, max_string_chars)

    if depth >= max_depth:
        if isinstance(value, dict):
            return {
                "_trimmed": True,
                "_type": "object",
                "_total_keys": len(value),
                "_sample_keys": list(value.keys())[: min(len(value), 5)],
            }
        if isinstance(value, list):
            return {
                "_trimmed": True,
                "_type": "array",
                "_total_items": len(value),
            }
        return value

    if isinstance(value, list):
        return [
            _shape_response_value(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_object_keys=max_object_keys,
                max_string_chars=max_string_chars,
            )
            for item in value[:max_items]
        ]

    if isinstance(value, dict):
        items = list(value.items())[:max_object_keys]
        return {
            key: _shape_response_value(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_object_keys=max_object_keys,
                max_string_chars=max_string_chars,
            )
            for key, item in items
        }

    return value


def _shape_response(body):
    shaped = _shape_response_value(
        body,
        depth=0,
        max_depth=RESPONSE_SHAPE_MAX_DEPTH,
        max_items=RESPONSE_SHAPE_MAX_ITEMS,
        max_object_keys=RESPONSE_SHAPE_MAX_OBJECT_KEYS,
        max_string_chars=RESPONSE_SHAPE_MAX_STRING_CHARS,
    )
    return shaped, {
        "body_shaped": True,
        "body_shape_options": {
            "max_depth": RESPONSE_SHAPE_MAX_DEPTH,
            "max_items": RESPONSE_SHAPE_MAX_ITEMS,
            "max_object_keys": RESPONSE_SHAPE_MAX_OBJECT_KEYS,
            "max_string_chars": RESPONSE_SHAPE_MAX_STRING_CHARS,
        },
    }


def _to_response_text(body) -> str:
    if isinstance(body, str):
        return body
    try:
        return json.dumps(body, ensure_ascii=False, default=str)
    except Exception:
        return str(body)


def _build_body_payload(body: Any) -> dict[str, Any]:
    text = _to_response_text(body)
    total_chars = len(text)
    full_chunks = (total_chars + RESPONSE_BODY_CHUNK_SIZE - 1) // RESPONSE_BODY_CHUNK_SIZE

    if total_chars <= RESPONSE_BODY_CHUNK_SIZE:
        return {
            "body": body,
            "body_chunked": False,
            "body_total_chars": total_chars,
        }

    visible_chars = RESPONSE_BODY_CHUNK_SIZE * RESPONSE_BODY_MAX_CHUNKS
    visible_text = text[:visible_chars]
    visible_chunks = [
        visible_text[i : i + RESPONSE_BODY_CHUNK_SIZE] for i in range(0, len(visible_text), RESPONSE_BODY_CHUNK_SIZE)
    ]

    return {
        "body": visible_chunks,
        "body_chunked": True,
        "body_chunk_size": RESPONSE_BODY_CHUNK_SIZE,
        "body_chunks_returned": len(visible_chunks),
        "body_total_chunks": full_chunks,
        "body_total_chars": total_chars,
        "body_truncated": total_chars > visible_chars,
        "body_truncated_chars": max(total_chars - visible_chars, 0),
    }


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
    ``limit``, ``maxResults``, ``pageSize``, or reduced ``expand`` when supported.
    Large response bodies are shaped and chunked to avoid context explosion.
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
        shaped_body, body_shape_meta = _shape_response(result.body)
        body_payload = _build_body_payload(shaped_body)
        return ToolResult.success(
            {
                "status_code": result.status_code,
                **body_payload,
                **body_shape_meta,
            },
            metadata={"elapsed_ms": result.elapsed_ms},
        )
