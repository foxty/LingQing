"""Unit tests for database query tools helper functions."""

import json

import pandas as pd
import pytest

from apps.shared.core.exceptions import AuthorizationError
from apps.tenant_app_service.agents.tools.database import (
    _format_response,
    run_sql_query_on_datasource,
)
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


class TestFormatResponse:
    """Test _format_response function."""

    def test_format_dataset(self):
        """Test formatting dataset."""
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["Alice", "Bob", "Charlie"], "age": [25, 30, 35]})

        data = _format_response(df, data_source_id=1)
        assert data["data_source_id"] == 1
        assert data["row_count"] == 3
        assert data["columns"] == ["id", "name", "age"]
        assert len(data["rows"]) == 3
        assert data["rows"][0] == {"id": 1, "name": "Alice", "age": 25}

    def test_format_truncates_long_strings(self):
        """Test that long strings are truncated."""
        long_text = "x" * 300
        df = pd.DataFrame({"id": [1], "description": [long_text]})

        data = _format_response(df, data_source_id=1)
        assert data["rows"][0]["description"].endswith("...[truncated]")
        # MAX_CELL_LENGTH (200) + len("...[truncated]") (14) = 214
        assert len(data["rows"][0]["description"]) == 214

    def test_format_empty_dataframe(self):
        """Test formatting empty dataframe."""
        df = pd.DataFrame({"id": [], "name": []})

        data = _format_response(df, data_source_id=1)
        assert data["row_count"] == 0
        assert data["rows"] == []
        assert data["columns"] == ["id", "name"]

    def test_format_handles_special_types(self):
        """Test formatting handles timestamps and other types."""
        df = pd.DataFrame(
            {
                "id": [1, 2],
                "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "amount": [100.5, 200.75],
            }
        )

        data = _format_response(df, data_source_id=1)
        assert data["row_count"] == 2
        assert len(data["rows"]) == 2
        # _format_response returns native values; ToolResult JSON coercion stringifies timestamps.
        assert isinstance(data["rows"][0]["timestamp"], (str, pd.Timestamp))
        assert isinstance(data["rows"][0]["amount"], float)


@pytest.mark.asyncio
async def test_run_sql_query_on_datasource_calls_query_data(monkeypatch, runnable_config):
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    captured: dict = {}

    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            captured["tenant_id"] = tenant_id

        async def query_data_for_actor(self, **kwargs):
            captured["query_kwargs"] = kwargs
            return pd.DataFrame([{"id": 1, "name": "Alice"}])

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.database.app_db_session", lambda: _FakeSessionContext()
    )
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.database.DataSourceService", _FakeService)

    result = await run_sql_query_on_datasource.ainvoke(
        {
            "data_source_id": 7,
            "sql_query": "SELECT * FROM orders",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert payload["data_source_id"] == 7
    assert payload["row_count"] == 1
    assert captured["tenant_id"] == 1
    assert captured["query_kwargs"]["data_source_id"] == 7
    assert captured["query_kwargs"]["actor"].user_id == 123
    assert captured["query_kwargs"]["actor"].user_role == "admin"
    assert captured["query_kwargs"]["max_rows"] == 200


@pytest.mark.asyncio
async def test_run_sql_query_on_datasource_returns_error_on_auth_block(monkeypatch, runnable_config):
    class _FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeService:
        def __init__(self, tenant_id, data_source_repo, asset_repo):
            pass

        async def query_data_for_actor(self, **kwargs):
            raise AuthorizationError("No permission to read asset 'orders'.")

    monkeypatch.setattr(
        "apps.tenant_app_service.agents.tools.database.app_db_session", lambda: _FakeSessionContext()
    )
    monkeypatch.setattr("apps.tenant_app_service.agents.tools.database.DataSourceService", _FakeService)

    result = await run_sql_query_on_datasource.ainvoke(
        {
            "data_source_id": 7,
            "sql_query": "SELECT * FROM orders",
        },
        config=runnable_config,
    )
    assert result.status == ToolResultStatus.ERROR
    assert "No permission" in result.error.message
