"""Generate compact API spec artifacts for agent tools from FastAPI OpenAPI."""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _bootstrap_minimal_env() -> None:
    """Set safe defaults so importing the FastAPI app works without .env.local."""
    if os.getenv("DATA_ROOT_PATH"):
        return

    os.environ.setdefault("DATA_ROOT_PATH", tempfile.mkdtemp(prefix="lingqing-spec-"))
    os.environ.setdefault("SECRET_KEY", "spec-check-secret")
    os.environ.setdefault("TENANT_APP_DB_USER", "test_user")
    os.environ.setdefault("TENANT_APP_DB_PASSWORD", "test_password")
    os.environ.setdefault("TENANT_APP_DB_NAME", "test_db")
    os.environ.setdefault("TENANT_APP_DB_HOST", "localhost")


_bootstrap_minimal_env()

from apps.tenant_app_service.server import app

OUTPUT_DIR = Path("config/agent_api")
INDEX_FILE = OUTPUT_DIR / "api_index.json"
SPECS_FILE = OUTPUT_DIR / "api_specs_compact.json"

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}
logger = logging.getLogger(__name__)


def _operation_id(method: str, path: str, operation: dict[str, Any]) -> str:
    existing = operation.get("operationId")
    if isinstance(existing, str) and existing.strip():
        return existing.strip()

    normalized_path = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    normalized_path = normalized_path or "root"
    return f"{method.lower()}_{normalized_path}"


def _operation_key(method: str, path: str) -> str:
    """Create readable operation key based on HTTP method + raw path."""
    return f"{method.upper()}_{path}"


def _risk_level(method: str) -> str:
    if method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return "read"
    if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        return "write"
    return "unknown"


def _extract_body_examples(operation: dict[str, Any]) -> list[dict[str, Any]]:
    request_body = operation.get("requestBody", {})
    if not isinstance(request_body, dict):
        return []

    content = request_body.get("content", {})
    if not isinstance(content, dict):
        return []

    json_content = content.get("application/json", {})
    if not isinstance(json_content, dict):
        return []

    examples: list[dict[str, Any]] = []

    if "example" in json_content:
        examples.append(json_content["example"])

    examples_map = json_content.get("examples", {})
    if isinstance(examples_map, dict):
        for _, payload in examples_map.items():
            if isinstance(payload, dict) and "value" in payload:
                examples.append(payload["value"])

    return examples


def _extract_required_body_fields(operation: dict[str, Any]) -> list[str]:
    request_body = operation.get("requestBody", {})
    if not isinstance(request_body, dict):
        return []

    content = request_body.get("content", {})
    if not isinstance(content, dict):
        return []

    json_content = content.get("application/json", {})
    if not isinstance(json_content, dict):
        return []

    schema = json_content.get("schema", {})
    if not isinstance(schema, dict):
        return []

    required = schema.get("required", [])
    if not isinstance(required, list):
        return []

    return [item for item in required if isinstance(item, str)]


def _extract_parameters(
    operation: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    path_params: list[dict[str, Any]] = []
    query_params: list[dict[str, Any]] = []
    header_params: list[dict[str, Any]] = []

    params = operation.get("parameters", [])
    if not isinstance(params, list):
        return path_params, query_params, header_params

    for param in params:
        if not isinstance(param, dict):
            continue

        item = {
            "name": param.get("name"),
            "required": bool(param.get("required", False)),
            "schema": param.get("schema", {}),
            "description": param.get("description", ""),
        }

        location = param.get("in")
        if location == "path":
            path_params.append(item)
        elif location == "query":
            query_params.append(item)
        elif location == "header":
            header_params.append(item)

    return path_params, query_params, header_params


def _extract_response_schema(operation: dict[str, Any]) -> tuple[str | None, dict[str, Any], list[str]]:
    responses = operation.get("responses", {})
    if not isinstance(responses, dict):
        return None, {}, []

    success_status = None
    success_schema: dict[str, Any] = {}

    for code in ("200", "201", "202", "204"):
        if code not in responses:
            continue
        success_status = code
        response_obj = responses.get(code, {})
        if isinstance(response_obj, dict):
            content = response_obj.get("content", {})
            if isinstance(content, dict):
                json_content = content.get("application/json", {})
                if isinstance(json_content, dict):
                    schema = json_content.get("schema", {})
                    if isinstance(schema, dict):
                        success_schema = schema
        break

    error_statuses = [code for code in responses.keys() if isinstance(code, str) and code.startswith(("4", "5"))]
    return success_status, success_schema, sorted(error_statuses)


def _compact(d: dict[str, Any]) -> dict[str, Any]:
    """Remove keys whose value is an empty list or empty dict."""
    return {k: v for k, v in d.items() if v != [] and v != {}}


def _build_payloads(generated_at: str) -> tuple[dict[str, Any], dict[str, Any], int]:
    openapi = app.openapi()
    paths = openapi.get("paths", {})
    components = openapi.get("components", {})

    operations_index: list[dict[str, Any]] = []
    operations_specs: dict[str, dict[str, Any]] = {}
    operation_keys: dict[str, str] = {}

    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue

        for method, operation in methods.items():
            if method.lower() not in HTTP_METHODS:
                continue
            if not isinstance(operation, dict):
                continue

            op_id = _operation_id(method, path, operation)
            op_key = _operation_key(method, path)

            path_params, query_params, header_params = _extract_parameters(operation)
            body_examples = _extract_body_examples(operation)
            body_required_fields = _extract_required_body_fields(operation)
            success_status, success_schema, error_statuses = _extract_response_schema(operation)
            summary = operation.get("summary", "")
            description = operation.get("description", "")

            operations_index.append(
                {
                    "operation_key": op_key,
                    "summary": summary,
                    # "description": description,
                    # "tags": operation.get("tags", []),
                    "risk_level": _risk_level(method),
                }
            )

            operations_specs[op_id] = {
                "operation_key": op_key,
                "method": method.upper(),
                "path": path,
                "summary": summary,
                "description": description,
                "request": _compact(
                    {
                        "path_params": path_params,
                        "query_params": query_params,
                        "header_params": header_params,
                        "body_required_fields": body_required_fields,
                        "body_schema": operation.get("requestBody", {}),
                        "body_examples": body_examples,
                    }
                ),
                "response": _compact(
                    {
                        "success_status": success_status,
                        "success_schema": success_schema,
                        "error_statuses": error_statuses,
                    }
                ),
                "constraints": {
                    "side_effect": _risk_level(method) != "read",
                    "idempotent": method.upper() in {"GET", "PUT", "DELETE", "HEAD", "OPTIONS"},
                },
            }
            operation_keys[op_key] = op_id

    index_payload = {
        "version": "v1",
        "generated_at": generated_at,
        "operations": sorted(operations_index, key=lambda item: item["operation_key"]),
    }
    specs_payload = {
        "version": "v1",
        "generated_at": generated_at,
        "components": components,
        "operation_keys": dict(sorted(operation_keys.items(), key=lambda item: item[0])),
        "operations": dict(sorted(operations_specs.items(), key=lambda item: item[0])),
    }
    return index_payload, specs_payload, len(operations_index)


def _strip_generated_at(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(payload)
    cleaned.pop("generated_at", None)
    return cleaned


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _preserve_generated_at_if_unchanged(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Keep existing generated_at when semantic content is unchanged."""
    if not path.exists():
        return payload
    try:
        existing = _read_json(path)
    except Exception:
        return payload
    if _strip_generated_at(existing) != _strip_generated_at(payload):
        return payload
    existing_generated_at = existing.get("generated_at")
    if isinstance(existing_generated_at, str) and existing_generated_at.strip():
        preserved = dict(payload)
        preserved["generated_at"] = existing_generated_at
        return preserved
    return payload


def _write_json_if_changed(path: Path, payload: dict[str, Any]) -> bool:
    """Write JSON only when content changed. Returns True if written."""
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if path.exists() and path.read_text(encoding="utf-8") == serialized:
        return False
    path.write_text(serialized, encoding="utf-8")
    return True


def generate() -> None:
    generated_at = datetime.now(UTC).isoformat()
    index_payload, specs_payload, operations_count = _build_payloads(generated_at=generated_at)
    index_payload = _preserve_generated_at_if_unchanged(INDEX_FILE, index_payload)
    specs_payload = _preserve_generated_at_if_unchanged(SPECS_FILE, specs_payload)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index_written = _write_json_if_changed(INDEX_FILE, index_payload)
    specs_written = _write_json_if_changed(SPECS_FILE, specs_payload)

    logger.info(
        "%s API index: %s",
        "Generated" if index_written else "Unchanged",
        INDEX_FILE,
    )
    logger.info(
        "%s compact specs: %s",
        "Generated" if specs_written else "Unchanged",
        SPECS_FILE,
    )
    logger.info("Operations: %s", operations_count)


def check() -> int:
    if not INDEX_FILE.exists() or not SPECS_FILE.exists():
        logger.error("Missing API spec artifacts. Run generator first.")
        return 1

    # Timestamp is intentionally excluded during check-only comparisons.
    index_payload, specs_payload, _ = _build_payloads(generated_at="CHECK_IGNORED")
    existing_index = _read_json(INDEX_FILE)
    existing_specs = _read_json(SPECS_FILE)

    if _strip_generated_at(index_payload) != _strip_generated_at(existing_index):
        logger.error("API index is out of date: %s", INDEX_FILE)
        return 1
    if _strip_generated_at(specs_payload) != _strip_generated_at(existing_specs):
        logger.error("API compact specs are out of date: %s", SPECS_FILE)
        return 1
    logger.info("API spec artifacts are up to date.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Generate/check compact agent API spec artifacts.")
    parser.add_argument("--check", action="store_true", help="Validate artifacts are up to date without rewriting files.")
    args = parser.parse_args()
    if args.check:
        raise SystemExit(check())
    generate()
