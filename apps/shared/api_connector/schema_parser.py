"""Schema ingestion and OpenAPI operation extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import aiohttp
import yaml

from apps.shared.api_connector.constants import (
    ALLOWED_HTTP_METHODS_LOWER,
    AUTH_REQUIREMENT_NONE,
    AUTH_REQUIREMENT_REQUIRED,
    SCHEMA_SOURCE_TYPE_MANUAL,
    SCHEMA_SOURCE_TYPE_OPENAPI_UPLOAD,
    SCHEMA_SOURCE_TYPE_OPENAPI_URL,
)
from apps.shared.api_connector.domain import AuthRequirement, SchemaSourceType
from apps.shared.api_connector.source_url_adapter import OpenApiSourceUrlAdapter
from apps.shared.core.exceptions import ValidationError

_ALLOWED_METHODS = ALLOWED_HTTP_METHODS_LOWER


@dataclass
class OperationSpec:
    """Extracted operation definition from external schema."""

    operation_uid_seed: str
    method: str
    path_template: str
    operation_id: str | None
    summary: str
    description: str | None
    tags: list[str]
    request_schema: dict[str, Any] | None
    response_schema: dict[str, Any] | None
    auth_requirement: AuthRequirement


class SchemaSourceResolver:
    """Load OpenAPI payload from URL or uploaded content."""

    @staticmethod
    async def resolve(
        source_type: SchemaSourceType,
        source_url: str | None = None,
        file_content: str | None = None,
    ) -> dict[str, Any] | None:
        if source_type == SCHEMA_SOURCE_TYPE_MANUAL:
            return None

        if source_type == SCHEMA_SOURCE_TYPE_OPENAPI_URL:
            if not source_url:
                raise ValidationError("schema_source_url is required for openapi_url")
            adapted = OpenApiSourceUrlAdapter.adapt(source_url)
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(adapted.url) as response:
                    if response.status >= 400:
                        raise ValidationError(
                            f"Failed to fetch schema from URL (HTTP {response.status}). "
                            "Please verify the URL is publicly accessible and points to a raw OpenAPI file."
                        )
                    content_type = (response.headers.get("Content-Type") or "").lower()
                    payload_text = await response.text()
            _raise_if_html_payload(
                payload_text, source_url=source_url, adapted_url=adapted.url, content_type=content_type
            )
            return _load_json_or_yaml(payload_text)

        if source_type == SCHEMA_SOURCE_TYPE_OPENAPI_UPLOAD:
            if not file_content:
                raise ValidationError("file_content is required for openapi_upload")
            return _load_json_or_yaml(file_content)

        raise ValidationError(f"Unsupported schema source type: {source_type}")


class OpenApiParser:
    """Parse OpenAPI schema into operation specs."""

    def __init__(self, schema: dict[str, Any]):
        self._schema = schema

    def parse(self) -> list[OperationSpec]:
        paths = self._schema.get("paths")
        if not isinstance(paths, dict):
            raise ValidationError("OpenAPI schema missing valid 'paths'")

        operations: list[OperationSpec] = []
        for path_template, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method not in _ALLOWED_METHODS or not isinstance(operation, dict):
                    continue
                request_schema = self._extract_request_schema(operation, path_item)
                response_schema = self._extract_response_schema(operation)
                operations.append(
                    OperationSpec(
                        operation_uid_seed=f"{method.upper()}:{path_template}:{operation.get('operationId', '')}",
                        method=method.upper(),
                        path_template=path_template,
                        operation_id=operation.get("operationId"),
                        summary=operation.get("summary") or "",
                        description=operation.get("description"),
                        tags=[str(tag) for tag in operation.get("tags", []) if isinstance(tag, str)],
                        request_schema=request_schema,
                        response_schema=response_schema,
                        auth_requirement=AUTH_REQUIREMENT_REQUIRED
                        if operation.get("security")
                        else AUTH_REQUIREMENT_NONE,
                    )
                )
        return operations

    def _extract_request_schema(self, operation: dict[str, Any], path_item: dict[str, Any]) -> dict[str, Any] | None:
        merged_parameters: list[dict[str, Any]] = []
        for source in (path_item.get("parameters", []), operation.get("parameters", [])):
            if isinstance(source, list):
                for param in source:
                    if isinstance(param, dict):
                        merged_parameters.append(param)

        request_body = operation.get("requestBody")
        if not merged_parameters and not request_body:
            return None

        return {
            "parameters": merged_parameters,
            "requestBody": request_body if isinstance(request_body, dict) else None,
        }

    def _extract_response_schema(self, operation: dict[str, Any]) -> dict[str, Any] | None:
        responses = operation.get("responses")
        if not isinstance(responses, dict):
            return None
        for status_code in ("200", "201", "202", "default"):
            candidate = responses.get(status_code)
            if isinstance(candidate, dict):
                return {
                    "status": status_code,
                    "schema": candidate,
                }
        return None


def _load_json_or_yaml(payload_text: str) -> dict[str, Any]:
    parsed: Any
    try:
        parsed = json.loads(payload_text)
    except json.JSONDecodeError:
        try:
            parsed = yaml.safe_load(payload_text)
        except yaml.YAMLError as exc:
            raise ValidationError(
                "Schema payload is not valid JSON/YAML. Please provide a valid OpenAPI document (JSON or YAML)."
            ) from exc

    if not isinstance(parsed, dict):
        raise ValidationError("Schema payload must be a JSON/YAML object")
    return parsed


def _raise_if_html_payload(
    payload_text: str,
    *,
    source_url: str,
    adapted_url: str,
    content_type: str,
) -> None:
    looks_like_html = (
        payload_text.lstrip().lower().startswith("<!doctype html") or "<html" in payload_text[:512].lower()
    )
    if "text/html" not in content_type and not looks_like_html:
        return

    source_host = urlparse(source_url).netloc
    adapted_host = urlparse(adapted_url).netloc
    if source_host in {"github.com", "www.github.com"} and adapted_host == "raw.githubusercontent.com":
        raise ValidationError(
            "Schema URL returned an HTML page instead of an OpenAPI file after GitHub URL adaptation. "
            "Please verify the target file exists and is publicly reachable."
        )

    raise ValidationError(
        "Schema URL returned an HTML page instead of an OpenAPI file. Please provide a direct raw JSON/YAML URL."
    )
