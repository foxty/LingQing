"""Unit tests for API connector agent tools."""

import json

import pytest

from apps.tenant_app_service.agents.tools.api_connector import (
    call_external_api,
    get_api_connector_info,
    get_api_operation_detail,
)
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


@pytest.mark.asyncio
async def test_get_api_operation_detail(monkeypatch, runnable_config):
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
    monkeypatch.setattr("apps.shared.external_systems.api_connector.service.ApiConnectorService", _FakeService)

    result = await get_api_operation_detail.ainvoke(
        {"operation_id": 10},
        config=runnable_config,
    )

    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["operation_uid"] == "uid-1"
    assert payload["method"] == "GET"
    assert "agent_instructions" not in payload


@pytest.mark.asyncio
async def test_get_api_connector_info(monkeypatch, runnable_config):
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeConnector:
        id = 9
        name = "test-connector"
        description = "Synthetic connector"
        base_url = "https://api.example.com"
        credential_mode = "user"
        user_connection_status = "connected"
        agent_instructions = "Use focused searches."

    class _FakeService:
        def __init__(self, tenant_id, db_session):
            self.tenant_id = tenant_id

        async def get_connector_for_actor(self, **kwargs):
            return _FakeConnector()

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.api_connector.app_db_session",
        lambda: _FakeSessionContext(),
    )
    monkeypatch.setattr("apps.shared.external_systems.api_connector.service.ApiConnectorService", _FakeService)

    result = await get_api_connector_info.ainvoke(
        {"connector_id": 9},
        config=runnable_config,
    )

    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["connector_id"] == 9
    assert payload["connection_status"] == "connected"
    assert payload["agent_instructions"] == "Use focused searches."


@pytest.mark.asyncio
async def test_call_external_api(monkeypatch, runnable_config):
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

    def _fake_execution_service(tenant_id, db_session):
        return _FakeExecService(tenant_id, db_session)

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.api_connector.api_connector_execution_service",
        _fake_execution_service,
    )

    result = await call_external_api.ainvoke(
        {
            "operation_id": 42,
            "parameters": {"path": {"id": "100"}},
        },
        config=runnable_config,
    )

    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.SUCCESS
    assert payload["status_code"] == 200
    assert payload["body"]["ok"] is True
