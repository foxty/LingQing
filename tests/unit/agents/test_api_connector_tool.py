"""Unit tests for API connector agent tools."""

import json

import pytest

from apps.tenant_app_service.agents.tools.api_connector import (
    RESPONSE_BODY_MAX_CHARS,
    _compact_api_body_for_agent,
    call_external_api,
    get_api_connector_info,
    get_api_operation_detail,
)
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


def _slack_like_search_body(*, match_count: int, text_chars: int = 800) -> dict:
    """Synthetic Slack search.messages-shaped payload (no production content)."""
    filler = "x" * text_chars
    return {
        "ok": True,
        "query": "synthetic-status-query",
        "messages": {
            "total": match_count + 60,
            "matches": [
                {
                    "iid": f"m{i}",
                    "user": f"U{i:04d}",
                    "username": f"user_{i}",
                    "ts": f"1700000000.{i:06d}",
                    "text": f"synthetic message {i}: {filler}",
                    "channel": {"id": f"C{i:04d}", "name": f"channel-{i}"},
                    "permalink": f"https://example.test/archives/C{i:04d}/p{i}",
                }
                for i in range(match_count)
            ],
        },
    }


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
    assert payload.get("body_truncated") is False
    assert isinstance(payload["body"], dict)


def test_compact_api_body_keeps_valid_json_for_large_lists():
    raw = _slack_like_search_body(match_count=20, text_chars=900)
    compacted, meta = _compact_api_body_for_agent(raw)

    assert isinstance(compacted, dict)
    assert not isinstance(compacted, list)
    assert meta["body_truncated"] is True
    assert "truncation_hint" in meta
    assert meta["body_returned_chars"] <= RESPONSE_BODY_MAX_CHARS
    # Re-serializing the tool envelope must stay parseable.
    envelope = json.loads(json.dumps({"body": compacted, **meta}, ensure_ascii=False, default=str))
    assert isinstance(envelope["body"], dict)
    matches = envelope["body"]["messages"]["matches"]
    assert isinstance(matches, list)
    assert 0 < len(matches) < 20
    assert "text" in matches[0]


def test_compact_api_body_small_payload_not_truncated():
    raw = _slack_like_search_body(match_count=2, text_chars=40)
    compacted, meta = _compact_api_body_for_agent(raw)

    assert meta["body_truncated"] is False
    assert "truncation_hint" not in meta
    assert isinstance(compacted, dict)
    assert len(compacted["messages"]["matches"]) == 2


@pytest.mark.asyncio
async def test_call_external_api_large_body_returns_partial(monkeypatch, runnable_config):
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeResult:
        status_code = 200
        headers = {}
        body = _slack_like_search_body(match_count=20, text_chars=900)
        elapsed_ms = 9.0
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
        "apps.tenant_app_service.agents.tools.api_connector.api_connector_execution_service",
        lambda tenant_id, db_session: _FakeExecService(tenant_id, db_session),
    )

    result = await call_external_api.ainvoke(
        {"operation_id": 1856, "parameters": {"query": {"count": "20"}}},
        config=runnable_config,
    )

    payload = json.loads(result.content)
    assert result.status == ToolResultStatus.PARTIAL
    assert payload["body_truncated"] is True
    assert isinstance(payload["body"], dict)
    assert "truncation_hint" in payload
    matches = payload["body"]["messages"]["matches"]
    assert isinstance(matches, list)
    assert len(matches) < 20
    assert "text" in matches[0]
