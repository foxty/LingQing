"""Agent tools for API connector invocation."""

from __future__ import annotations

import json

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.shared.api_connector.execution import ApiConnectorExecutionService
from apps.shared.api_connector.schemas import ApiOperationCallParameters
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.tenant_app_service.agents.context import delegated_api_connector_ids, extract_runtime_context
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


def _build_body_payload(body: dict) -> dict[str, any]:
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


class ApiConnectorToolInput(BaseModel):
    """Input schema for API connector invocation tool."""

    action: str = Field(
        ...,
        description="One of: get_operation_detail, call_external_api",
    )
    operation_id: int = Field(..., description="Internal operation ID for detail/call")
    parameters: ApiOperationCallParameters = Field(
        default_factory=ApiOperationCallParameters,
        description="Call parameters for action=call_external_api",
    )


@tool(args_schema=ApiConnectorToolInput)
async def api_connector(
    action: str,
    config: RunnableConfig,
    operation_id: int,
    parameters: ApiOperationCallParameters | None = None,
) -> ToolResult:
    """Inspect and invoke external API operations via API connectors.

    Supported actions:
    1. ``get_operation_detail``
      - Purpose: retrieve detailed schema information for one operation.
      - Required args: ``operation_id``.
      - Returns: operation metadata plus ``request_schema`` and ``response_schema``.

    2. ``call_external_api``
      - Purpose: execute one external operation with runtime parameters.
      - Required args: ``operation_id``.
      - Optional args: ``parameters`` (defaults to empty dict).
        - Prefer upstream filtering/pagination in ``parameters.query`` such as ``fields``, ``limit``,
          ``maxResults``, ``pageSize``, or reduced ``expand`` when the target API supports them.
      - Returns on success: response envelope with ``status_code`` and controlled-size ``body``.
        - When body is large, ``body`` is returned as chunk list with chunk metadata to avoid
          context explosion.
      - Returns on failure: ``ToolResult`` error with code ``API_CONNECTOR_CALL_FAILED`` and
        metadata including ``status_code`` and ``elapsed_ms``.

    Recommended call flow:
    Use ``search_apis`` to find operations, then ``get_operation_detail`` (when contract is unclear),
    then ``call_external_api``.

    Notes:
    - ``action`` must be one of: ``get_operation_detail``, ``call_external_api``.
    - Missing required fields return ``API_CONNECTOR_BAD_REQUEST``.
    - Runtime context extraction failures return ``API_CONNECTOR_INVALID_CONTEXT``.
    """
    try:
        runtime = extract_runtime_context(config)
    except ValueError as exc:
        return ToolResult.error_result(str(exc), code="API_CONNECTOR_INVALID_CONTEXT")

    async with app_db_session() as session:
        actor = ActorContext(
            tenant_id=runtime.user.tenant_id,
            user_id=runtime.user.user_id,
            user_role=runtime.user.role,
        )

        from apps.shared.api_connector.service import ApiConnectorService

        service = ApiConnectorService(tenant_id=runtime.user.tenant_id, db_session=session)

        attached_ids = delegated_api_connector_ids(runtime.capability_profile)
        allowed_ids = runtime.capability_profile.allowed_api_connector_ids if runtime.capability_profile else None

        if action == "get_operation_detail":
            row, connector = await service.get_operation_by_id_for_actor(
                operation_id=operation_id,
                actor=actor,
                delegated_ids=attached_ids,
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

        if action == "call_external_api":
            if allowed_ids is not None:
                _row, connector = await service.get_operation_by_id_for_actor(
                    operation_id=operation_id,
                    actor=actor,
                    delegated_ids=attached_ids,
                )
                if connector.id not in allowed_ids:
                    return ToolResult.error_result("Access denied to API operation", code="API_CONNECTOR_FORBIDDEN")
            exec_service = ApiConnectorExecutionService(tenant_id=runtime.user.tenant_id, db_session=session)
            result = await exec_service.execute_operation_by_id_for_actor(
                operation_id=operation_id,
                actor=actor,
                parameters=parameters or ApiOperationCallParameters(),
                delegated_ids=attached_ids,
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

    return ToolResult.error_result(
        f"Unsupported action: {action}",
        code="API_CONNECTOR_BAD_REQUEST",
    )
