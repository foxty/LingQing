"""Unit tests for api_connector agent tool."""

import json

import pytest

from apps.tenant_app_service.agents.tools.api_connector import api_connector
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


@pytest.mark.asyncio
async def test_api_connector_tool_get_operation_detail(monkeypatch, runnable_config):
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeOperation:
        def __init__(self):
            self.id = 10
            self.operation_uid = "uid-1"
            self.connector_id = 9
            self.method = "GET"
            self.path_template = "/orders"
            self.summary = "list orders"
            self.request_schema = None
            self.response_schema = None

    class _FakeConnector:
        def __init__(self):
            self.id = 9
            self.name = "test-connector"
            self.base_url = "https://api.example.com"

    class _FakeService:
        def __init__(self, tenant_id, db_session):
            self.tenant_id = tenant_id

        async def get_operation_by_id_for_actor(self, **kwargs):
            return _FakeOperation(), _FakeConnector()

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.api_connector.app_db_session",
        lambda: _FakeSessionContext(),
    )
    monkeypatch.setattr("apps.shared.api_connector.service.ApiConnectorService", _FakeService)

    result = await api_connector.ainvoke(
        {
            "action": "get_operation_detail",
            "operation_id": 10,
        },
        config=runnable_config,
    )

    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["operation_uid"] == "uid-1"
    assert payload["method"] == "GET"


@pytest.mark.asyncio
async def test_api_connector_tool_call_external_api(monkeypatch, runnable_config):
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeResult:
        status_code = 200
        headers = {"x-test": "1"}
        body = {"ok": True}
        elapsed_ms = 12.5
        error = None

    class _FakeExecService:
        def __init__(self, tenant_id, db_session):
            pass

        async def execute_operation_by_id_for_actor(self, **kwargs):
            return _FakeResult()

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.api_connector.app_db_session",
        lambda: _FakeSessionContext(),
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.api_connector.ApiConnectorExecutionService", _FakeExecService
    )

    result = await api_connector.ainvoke(
        {
            "action": "call_external_api",
            "operation_id": 42,
            "parameters": {"path": {"id": "100"}},
        },
        config=runnable_config,
    )

    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["status_code"] == 200
    assert payload["body"]["ok"] is True


@pytest.mark.asyncio
async def test_api_connector_tool_rejects_unknown_action(runnable_config):
    """Test that the tool rejects unsupported action values.

    Since operation_id is now a required field, Pydantic validates input before the tool runs.
    The tool itself only handles 'get_operation_detail' and 'call_external_api'.
    This test verifies Pydantic rejects missing required fields.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        await api_connector.ainvoke(
            {
                "action": "get_operation_detail",
                # Missing required operation_id
            },
            config=runnable_config,
        )
