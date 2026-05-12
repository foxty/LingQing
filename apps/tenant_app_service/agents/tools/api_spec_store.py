"""Utilities for loading generated API spec artifacts for agent tools."""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any


def _get_project_root() -> Path:
    """Return project root from current module location."""
    # .../apps/tenant_app_service/agents/tools/<this_file>
    return Path(__file__).resolve().parents[4]


def get_agent_api_spec_dir() -> Path:
    """Resolve API spec artifact directory.

    Can be overridden with AGENT_API_SPEC_DIR for testing.
    """
    override = os.getenv("AGENT_API_SPEC_DIR", "").strip()
    if override:
        return Path(override)
    return _get_project_root() / "config" / "agent_api"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"API spec file not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid API spec file format (expected object): {path}")
    return data


@lru_cache(maxsize=1)
def load_api_index() -> dict[str, Any]:
    """Load agent API index artifact."""
    path = get_agent_api_spec_dir() / "api_index.json"
    return _read_json(path)


@lru_cache(maxsize=1)
def load_api_specs_compact() -> dict[str, Any]:
    """Load compact API spec artifact."""
    path = get_agent_api_spec_dir() / "api_specs_compact.json"
    return _read_json(path)


def _normalize_operation_ref(operation_ref: str) -> str:
    return operation_ref.strip()


def resolve_operation_id(operation_ref: str) -> str | None:
    """Resolve operation_key to the internal operation_id used as key in compact specs."""
    ref = _normalize_operation_ref(operation_ref)
    if not ref:
        return None

    specs = load_api_specs_compact()
    operation_keys = specs.get("operation_keys", {})
    if isinstance(operation_keys, dict):
        mapped = operation_keys.get(ref)
        if isinstance(mapped, str) and mapped:
            return mapped

    return None


def get_operation(operation_ref: str) -> dict[str, Any] | None:
    """Get operation metadata by operation_key."""
    ref = _normalize_operation_ref(operation_ref)
    if not ref:
        return None

    index_data = load_api_index()
    for operation in index_data.get("operations", []):
        if operation.get("operation_key") == ref:
            return operation
    return None


def get_operation_spec(operation_ref: str) -> dict[str, Any] | None:
    """Get compact operation spec by operation_id or operation_key."""
    op_id = resolve_operation_id(operation_ref)
    if not op_id:
        return None

    specs = load_api_specs_compact()
    operations = specs.get("operations", {})
    return operations.get(op_id)


def clear_api_spec_cache() -> None:
    """Clear in-memory API spec caches (mainly for tests)."""
    load_api_index.cache_clear()
    load_api_specs_compact.cache_clear()
