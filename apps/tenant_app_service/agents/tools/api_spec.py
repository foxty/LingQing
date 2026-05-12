"""Tools for loading API schema snippets from generated OpenAPI artifacts."""

from copy import deepcopy
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.tools.api_spec_store import (
    get_operation,
    get_operation_spec,
    load_api_specs_compact,
)
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)

MAX_OPERATIONS_PER_CALL = 5


class LoadApiSpecSchema(BaseModel):
    """Schema for load_api_spec tool."""

    operation_refs: list[str] = Field(
        ...,
        description="List of operation_key references (e.g. 'GET_/data-sources', 'POST_/dashboards') to load.",
        min_length=1,
        max_length=MAX_OPERATIONS_PER_CALL,
    )


def _resolve_ref_pointer(ref: str, components: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve local OpenAPI refs like #/components/schemas/Model."""
    if not ref.startswith("#/components/"):
        return None

    parts = ref.lstrip("#/").split("/")
    node: Any = {"components": components}
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]

    return node if isinstance(node, dict) else None


def _expand_refs(value: Any, components: dict[str, Any], seen_refs: set[str] | None = None) -> Any:
    """Recursively inline $ref objects for LLM-friendly schema consumption."""
    if seen_refs is None:
        seen_refs = set()

    if isinstance(value, list):
        return [_expand_refs(item, components, seen_refs.copy()) for item in value]

    if not isinstance(value, dict):
        return value

    if "$ref" in value and isinstance(value["$ref"], str):
        ref = value["$ref"]
        if ref in seen_refs:
            return {"$ref": ref, "_ref_cycle": True}

        target = _resolve_ref_pointer(ref, components)
        if not target:
            return value

        seen_refs.add(ref)
        expanded_target = _expand_refs(deepcopy(target), components, seen_refs)

        # Merge non-$ref sibling keys into resolved object (OpenAPI semantics).
        siblings = {k: v for k, v in value.items() if k != "$ref"}
        if siblings and isinstance(expanded_target, dict):
            merged = dict(expanded_target)
            for k, v in siblings.items():
                merged[k] = _expand_refs(v, components, seen_refs.copy())
            return merged
        return expanded_target

    return {k: _expand_refs(v, components, seen_refs.copy()) for k, v in value.items()}


def _extract_json_body_schema(request_body_schema: dict[str, Any]) -> dict[str, Any]:
    """Extract application/json schema from OpenAPI requestBody object."""
    if not isinstance(request_body_schema, dict):
        return {}

    content = request_body_schema.get("content", {})
    if not isinstance(content, dict):
        return {}

    json_content = content.get("application/json", {})
    if not isinstance(json_content, dict):
        return {}

    schema = json_content.get("schema", {})
    return schema if isinstance(schema, dict) else {}


def _build_resolved_structures(operation_spec: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Build fully expanded request/response structure for direct LLM use."""
    request = operation_spec.get("request", {})
    response = operation_spec.get("response", {})

    def _resolve_params(params: Any) -> list[dict[str, Any]]:
        if not isinstance(params, list):
            return []
        resolved: list[dict[str, Any]] = []
        for param in params:
            if not isinstance(param, dict):
                continue
            resolved_param = dict(param)
            schema = resolved_param.get("schema", {})
            if isinstance(schema, dict):
                resolved_param["schema"] = _expand_refs(schema, components)
            resolved.append(resolved_param)
        return resolved

    body_schema = _extract_json_body_schema(request.get("body_schema", {}))
    response_schema = response.get("success_schema", {})

    return {
        "request_structure": {
            "path_params": _resolve_params(request.get("path_params", [])),
            "query_params": _resolve_params(request.get("query_params", [])),
            "header_params": _resolve_params(request.get("header_params", [])),
            "body_required_fields": request.get("body_required_fields", []),
            "json_body_schema": _expand_refs(body_schema, components) if body_schema else {},
        },
        "response_structure": {
            "success_status": response.get("success_status"),
            "json_schema": _expand_refs(response_schema, components) if isinstance(response_schema, dict) else {},
            "error_statuses": response.get("error_statuses", []),
        },
    }


@tool(args_schema=LoadApiSpecSchema)
async def load_api_spec(operation_refs: list[str]) -> ToolResult:
    """Load detailed API schema by operation reference from generated API spec artifacts.

    Use this tool before calling complex APIs to get required fields and examples.
    """
    if len(operation_refs) > MAX_OPERATIONS_PER_CALL:
        return ToolResult.error_result(
            code="API_SPEC_TOO_MANY_OPERATIONS",
            message=f"Too many operation_refs. Max allowed is {MAX_OPERATIONS_PER_CALL}.",
            metadata={"count": len(operation_refs)},
        )

    loaded_operations: list[dict] = []
    not_found: list[str] = []
    components = load_api_specs_compact().get("components", {})
    if not isinstance(components, dict):
        components = {}

    for operation_ref in operation_refs:
        operation_meta = get_operation(operation_ref)
        operation_spec = get_operation_spec(operation_ref)

        if not operation_meta or not operation_spec:
            not_found.append(operation_ref)
            continue

        resolved_structures = _build_resolved_structures(operation_spec, components)

        loaded_operations.append(
            {
                "operation_ref": operation_ref,
                "operation_key": operation_spec.get("operation_key"),
                "method": operation_spec.get("method"),
                "path": operation_spec.get("path"),
                "risk_level": operation_meta.get("risk_level", "unknown"),
                "request_structure": resolved_structures["request_structure"],
                "response_structure": resolved_structures["response_structure"],
            }
        )

    logger.debug(
        "Loaded API specs",
        extra={
            "requested": operation_refs,
            "loaded": len(loaded_operations),
            "missing": not_found,
        },
    )

    return ToolResult.success(
        {
            "loaded_count": len(loaded_operations),
            "not_found": not_found,
            "operations": loaded_operations,
        }
    )
