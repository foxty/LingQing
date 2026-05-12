import json

import pytest

from apps.tenant_app_service.agents.tools.api_spec import _expand_refs, load_api_spec
from apps.tenant_app_service.agents.tools.api_spec_store import clear_api_spec_cache
from apps.tenant_app_service.agents.tools.platform_api import call_platform_api
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


@pytest.fixture
def api_spec_artifacts(tmp_path, monkeypatch):
    spec_dir = tmp_path / "agent_api"
    spec_dir.mkdir()

    index_payload = {
        "version": "v1",
        "operations": [
            {
                "operation_key": "GET_/data-sources",
                "summary": "List data sources",
                "risk_level": "read",
            },
            {
                "operation_key": "PUT_/dashboards/{dashboard_id}",
                "summary": "Update dashboard",
                "risk_level": "write",
            },
        ],
    }

    specs_payload = {
        "version": "v1",
        "operation_keys": {
            "GET_/data-sources": "listDataSources",
            "PUT_/dashboards/{dashboard_id}": "updateDashboard",
        },
        "operations": {
            "listDataSources": {
                "operation_key": "GET_/data-sources",
                "method": "GET",
                "path": "/data-sources",
                "request": {
                    "path_params": [],
                    "query_params": [],
                    "header_params": [],
                    "body_required_fields": [],
                    "body_schema": {},
                    "body_examples": [],
                },
                "response": {
                    "success_status": "200",
                    "success_schema": {"type": "object"},
                    "error_statuses": ["401", "403"],
                },
                "constraints": {"side_effect": False, "idempotent": True},
                "human_notes": "List available data sources",
            },
            "updateDashboard": {
                "operation_key": "PUT_/dashboards/{dashboard_id}",
                "method": "PUT",
                "path": "/dashboards/{dashboard_id}",
                "request": {
                    "path_params": [{"name": "dashboard_id", "required": True, "schema": {"type": "integer"}}],
                    "query_params": [],
                    "header_params": [],
                    "body_required_fields": ["name"],
                    "body_schema": {},
                    "body_examples": [{"name": "Ops Dashboard"}],
                },
                "response": {
                    "success_status": "200",
                    "success_schema": {"type": "object"},
                    "error_statuses": ["400", "401", "403", "404", "422"],
                },
                "constraints": {"side_effect": True, "idempotent": True},
                "human_notes": "Update dashboard name/config",
            },
        },
    }

    (spec_dir / "api_index.json").write_text(json.dumps(index_payload), encoding="utf-8")
    (spec_dir / "api_specs_compact.json").write_text(json.dumps(specs_payload), encoding="utf-8")

    monkeypatch.setenv("AGENT_API_SPEC_DIR", str(spec_dir))
    clear_api_spec_cache()
    yield spec_dir
    clear_api_spec_cache()


@pytest.mark.asyncio
async def test_load_api_spec_returns_resolved_structures(api_spec_artifacts):
    result = await load_api_spec.coroutine(operation_refs=["GET_/data-sources"])
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert payload["loaded_count"] == 1
    assert payload["not_found"] == []
    operation = payload["operations"][0]
    assert operation["operation_key"] == "GET_/data-sources"
    assert operation["response_structure"]["success_status"] == "200"
    assert operation["request_structure"]["path_params"] == []
    assert operation["request_structure"]["query_params"] == []


@pytest.mark.asyncio
async def test_load_api_spec_resolves_param_schema(api_spec_artifacts):
    result = await load_api_spec.coroutine(operation_refs=["PUT_/dashboards/{dashboard_id}"])
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    operation = payload["operations"][0]
    assert operation["operation_key"] == "PUT_/dashboards/{dashboard_id}"
    assert operation["request_structure"]["path_params"][0]["schema"]["type"] == "integer"
    assert operation["request_structure"]["body_required_fields"] == ["name"]


@pytest.mark.asyncio
async def test_call_platform_api_requires_runtime_jwt(api_spec_artifacts, runnable_config):
    result = await call_platform_api.coroutine(
        method="GET",
        path="/data-sources",
        path_params={},
        query_params={},
        body=None,
        timeout_seconds=5,
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.metadata["ok"] is False
    assert result.metadata["status_code"] == 401
    assert "JWT token" in result.error.message


@pytest.mark.asyncio
async def test_call_platform_api_handles_missing_runnable_config(api_spec_artifacts):
    result = await call_platform_api.coroutine(
        method="GET",
        path="/data-sources",
        path_params={},
        query_params={},
        body=None,
        timeout_seconds=5,
        config=None,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.metadata["ok"] is False
    assert result.metadata["status_code"] == 400
    assert "RunnableConfig is required" in result.error.message


@pytest.mark.asyncio
async def test_call_platform_api_validates_required_fields(api_spec_artifacts, runnable_config):
    runnable_config["configurable"]["runtime"]["user"]["access_token"] = "jwt-token-123"

    result = await call_platform_api.coroutine(
        method="PUT",
        path="/dashboards/{dashboard_id}",
        path_params={},
        query_params={},
        body={},
        timeout_seconds=5,
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.metadata["ok"] is False
    assert result.metadata["status_code"] == 400
    assert result.error.message == "Missing required path parameters"


@pytest.mark.asyncio
async def test_call_platform_api_rejects_invalid_http_method(api_spec_artifacts, runnable_config):
    runnable_config["configurable"]["runtime"]["user"]["access_token"] = "jwt-token-123"

    result = await call_platform_api.coroutine(
        method="FOO",
        path="/dashboards/1",
        path_params={},
        query_params={},
        body={},
        timeout_seconds=5,
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.metadata["ok"] is False
    assert result.metadata["status_code"] == 400
    assert result.error.message == "Invalid HTTP method: FOO"


@pytest.mark.asyncio
async def test_call_platform_api_requires_path_starting_with_slash(api_spec_artifacts, runnable_config):
    runnable_config["configurable"]["runtime"]["user"]["access_token"] = "jwt-token-123"

    result = await call_platform_api.coroutine(
        method="POST",
        path="dashboards/1",
        path_params={},
        query_params={},
        body={},
        timeout_seconds=5,
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.metadata["ok"] is False
    assert result.metadata["status_code"] == 400
    assert result.error.message == "Invalid path: dashboards/1"


@pytest.mark.asyncio
async def test_call_platform_api_generic_mode_without_operation_ref(api_spec_artifacts, runnable_config):
    result = await call_platform_api.coroutine(
        method="GET",
        path="/health",
        path_params={},
        query_params={},
        body=None,
        timeout_seconds=5,
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert result.metadata["status_code"] == 401
    assert result.error.code == "PLATFORM_API_MISSING_TOKEN"


@pytest.mark.asyncio
async def test_call_platform_api_forwards_agent_context_headers(api_spec_artifacts, runnable_config, monkeypatch):
    runnable_config["configurable"]["runtime"]["user"]["access_token"] = "jwt-token-123"

    captured_headers = {}

    class _FakeResponse:
        status = 200

        async def text(self) -> str:
            return '{"ok": true}'

    class _FakeRequestContext:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeClientSession:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def request(self, *, headers, **kwargs):
            captured_headers.update(headers)
            return _FakeRequestContext()

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.platform_api.aiohttp.ClientSession",
        _FakeClientSession,
    )

    result = await call_platform_api.coroutine(
        method="POST",
        path="/dashboards",
        path_params={},
        query_params={},
        body={"name": "Test", "description": None, "config": {}},
        timeout_seconds=5,
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert payload["ok"] is True
    assert captured_headers["X-Agent-Request"] == "true"
    assert captured_headers["X-Agent-Thread-Id"] == "thread_test_123"
    assert captured_headers["X-Agent-Session-Id"] == "session_test_456"
    assert captured_headers["X-Agent-Id"] == "456"
    assert captured_headers["X-Agent-Name"] == "test_agent"
    assert "X-Agent-Context" not in captured_headers


# ---------------------------------------------------------------------------
# Fixture: specs that include $ref components
# ---------------------------------------------------------------------------


@pytest.fixture
def api_spec_with_refs(tmp_path, monkeypatch):
    """Fixture whose api_specs_compact.json contains a components block with $ref usage."""
    spec_dir = tmp_path / "agent_api"
    spec_dir.mkdir()

    index_payload = {
        "version": "v1",
        "operations": [
            {
                "operation_key": "POST_/items",
                "summary": "Create item",
                "risk_level": "write",
            },
        ],
    }

    specs_payload = {
        "version": "v1",
        "operation_keys": {"POST_/items": "createItem"},
        "operations": {
            "createItem": {
                "operation_key": "POST_/items",
                "method": "POST",
                "path": "/items",
                "request": {
                    "path_params": [
                        {
                            "name": "category_id",
                            "required": True,
                            # $ref in a path-param schema
                            "schema": {"$ref": "#/components/schemas/ItemId"},
                        }
                    ],
                    "query_params": [],
                    "header_params": [],
                    "body_required_fields": ["name"],
                    # Full OpenAPI requestBody shape so _extract_json_body_schema works
                    "body_schema": {
                        "content": {"application/json": {"schema": {"$ref": "#/components/schemas/CreateItemRequest"}}}
                    },
                    "body_examples": [],
                },
                "response": {
                    "success_status": "201",
                    # $ref directly in success_schema
                    "success_schema": {"$ref": "#/components/schemas/Item"},
                    "error_statuses": ["400", "422"],
                },
            },
        },
        "components": {
            "schemas": {
                "ItemId": {"type": "integer"},
                "CreateItemRequest": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        # nested $ref — resolved transitively
                        "details": {"$ref": "#/components/schemas/ItemDetails"},
                    },
                },
                "Item": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "string"},
                    },
                },
                "ItemDetails": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                    },
                },
                # Circular pair: NodeA <-> NodeB
                "NodeA": {"$ref": "#/components/schemas/NodeB"},
                "NodeB": {"$ref": "#/components/schemas/NodeA"},
            }
        },
    }

    (spec_dir / "api_index.json").write_text(json.dumps(index_payload), encoding="utf-8")
    (spec_dir / "api_specs_compact.json").write_text(json.dumps(specs_payload), encoding="utf-8")

    monkeypatch.setenv("AGENT_API_SPEC_DIR", str(spec_dir))
    clear_api_spec_cache()
    yield spec_dir
    clear_api_spec_cache()


# ---------------------------------------------------------------------------
# load_api_spec integration tests — $ref resolution through the tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_api_spec_resolves_body_schema_ref(api_spec_with_refs):
    result = await load_api_spec.coroutine(operation_refs=["POST_/items"])
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    body_schema = payload["operations"][0]["request_structure"]["json_body_schema"]
    assert body_schema["type"] == "object"
    assert "name" in body_schema["properties"]


@pytest.mark.asyncio
async def test_load_api_spec_resolves_success_schema_ref(api_spec_with_refs):
    result = await load_api_spec.coroutine(operation_refs=["POST_/items"])
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    json_schema = payload["operations"][0]["response_structure"]["json_schema"]
    assert json_schema["type"] == "object"
    assert "id" in json_schema["properties"]


@pytest.mark.asyncio
async def test_load_api_spec_resolves_path_param_schema_ref(api_spec_with_refs):
    result = await load_api_spec.coroutine(operation_refs=["POST_/items"])
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    path_params = payload["operations"][0]["request_structure"]["path_params"]
    assert path_params[0]["schema"] == {"type": "integer"}


@pytest.mark.asyncio
async def test_load_api_spec_resolves_nested_refs(api_spec_with_refs):
    """CreateItemRequest.details is a $ref to ItemDetails — must be transitively inlined."""
    result = await load_api_spec.coroutine(operation_refs=["POST_/items"])
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    body_schema = payload["operations"][0]["request_structure"]["json_body_schema"]
    details = body_schema["properties"]["details"]
    assert details["type"] == "object"
    assert "description" in details["properties"]


# ---------------------------------------------------------------------------
# _expand_refs unit tests — edge cases
# ---------------------------------------------------------------------------


def test_expand_refs_inlines_component_ref():
    components = {"schemas": {"Foo": {"type": "string", "example": "bar"}}}
    result = _expand_refs({"$ref": "#/components/schemas/Foo"}, components)
    assert result == {"type": "string", "example": "bar"}


def test_expand_refs_returns_as_is_for_external_ref():
    """External (non-component-local) $ref pointers are not resolvable and returned unchanged."""
    value = {"$ref": "https://example.com/schemas/Foo"}
    assert _expand_refs(value, {}) == value


def test_expand_refs_detects_cycle():
    components = {
        "schemas": {
            "NodeA": {"$ref": "#/components/schemas/NodeB"},
            "NodeB": {"$ref": "#/components/schemas/NodeA"},
        }
    }
    result = _expand_refs({"$ref": "#/components/schemas/NodeA"}, components)
    assert result.get("_ref_cycle") is True


def test_expand_refs_merges_sibling_keys():
    """Sibling keys alongside $ref are merged into the resolved schema (OpenAPI semantics)."""
    components = {
        "schemas": {
            "Base": {
                "type": "object",
                "properties": {"id": {"type": "integer"}},
            }
        }
    }
    result = _expand_refs(
        {"$ref": "#/components/schemas/Base", "description": "An extended base object"},
        components,
    )
    assert result["type"] == "object"
    assert result["description"] == "An extended base object"
    assert "id" in result["properties"]


def test_expand_refs_handles_list_of_schemas():
    components = {"schemas": {"Tag": {"type": "string"}}}
    result = _expand_refs(
        [{"$ref": "#/components/schemas/Tag"}, {"type": "integer"}],
        components,
    )
    assert result == [{"type": "string"}, {"type": "integer"}]


def test_expand_refs_returns_scalar_unchanged():
    assert _expand_refs("hello", {}) == "hello"
    assert _expand_refs(42, {}) == 42
    assert _expand_refs(None, {}) is None
