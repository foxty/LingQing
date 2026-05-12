"""Unit tests for report tools."""

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pydantic
import pytest
from langchain_core.runnables import RunnableConfig

from apps.tenant_app_service.agents.tools import report as report_tool
from apps.tenant_app_service.agents.tools.tool_result import ToolResultStatus


class _FakeSessionContext:
    class _Session:
        async def commit(self):
            return None

    async def __aenter__(self):
        return self._Session()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _fake_agent_tool_db_session(_config):
    return _FakeSessionContext()


class _FakeArtifact:
    def model_dump(self):
        return {"id": 1}


@pytest.mark.asyncio
async def test_create_report_tool_validates_format(monkeypatch, runnable_config):
    captured: dict = {}

    async def _fake_create_report(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            report=SimpleNamespace(id=17, title=kwargs["title"], format=kwargs.get("format") or "markdown"),
            artifact=_FakeArtifact(),
        )

    async def _allow(*args, **kwargs):
        return None

    fake_service = SimpleNamespace(create_report=_fake_create_report)

    monkeypatch.setattr(report_tool, "agent_tool_db_session", _fake_agent_tool_db_session)
    monkeypatch.setattr(report_tool, "tool_rbac_denied", _allow)
    monkeypatch.setattr(report_tool.ReportService, "create", lambda tenant_id, db_session: fake_service)

    content = "A" * 350
    result = await report_tool.create_report.ainvoke(
        {
            "title": "HTML Report",
            "content": content,
            "format": "html",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert captured["title"] == "HTML Report"
    assert captured["format"] == "html"
    assert captured["report_metadata"]["length"] == 350
    assert payload["report_id"] == 17
    assert payload["report_url"] == "/reports/17"


@pytest.mark.asyncio
async def test_create_report_tool_uses_runtime_db_session(monkeypatch, runnable_config):
    runtime_session = object()
    captured_session: dict = {}

    class _PassthroughSessionContext:
        def __init__(self, session):
            self._session = session

        async def __aenter__(self):
            return self._session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _runtime_agent_tool_db_session(config):
        session = config.get("configurable", {}).get("db_session")
        assert session is runtime_session
        return _PassthroughSessionContext(session)

    async def _fake_create_report(**kwargs):
        return SimpleNamespace(
            report=SimpleNamespace(id=21, title=kwargs["title"], format="markdown"),
            artifact=_FakeArtifact(),
        )

    async def _allow(*args, **kwargs):
        return None

    fake_service = SimpleNamespace(create_report=_fake_create_report)

    def _capture_service_create(tenant_id, db_session):
        captured_session["session"] = db_session
        return fake_service

    monkeypatch.setattr(report_tool, "agent_tool_db_session", _runtime_agent_tool_db_session)
    monkeypatch.setattr(report_tool, "tool_rbac_denied", _allow)
    monkeypatch.setattr(report_tool.ReportService, "create", _capture_service_create)

    config = RunnableConfig(
        configurable={
            **runnable_config["configurable"],
            "db_session": runtime_session,
        }
    )

    result = await report_tool.create_report.ainvoke(
        {
            "title": "Scheduled Report",
            "content": "body",
        },
        config=config,
    )

    assert result.status == ToolResultStatus.SUCCESS
    assert captured_session["session"] is runtime_session


@pytest.mark.asyncio
async def test_create_report_tool_rejects_invalid_format(monkeypatch, runnable_config):
    async def _allow(*args, **kwargs):
        return None

    fake_service = SimpleNamespace()

    monkeypatch.setattr(report_tool, "agent_tool_db_session", _fake_agent_tool_db_session)
    monkeypatch.setattr(report_tool, "tool_rbac_denied", _allow)
    monkeypatch.setattr(report_tool.ReportService, "create", lambda tenant_id, db_session: fake_service)

    with pytest.raises(pydantic.ValidationError):
        await report_tool.create_report.ainvoke(
            {
                "title": "Invalid Format Report",
                "content": "content",
                "format": "xml",
            },
            config=runnable_config,
        )


@pytest.mark.asyncio
async def test_get_report_tool_returns_report_payload(monkeypatch, runnable_config):
    captured: dict = {}

    async def _fake_get_report_for_actor(report_id: int, *, actor):
        captured["report_id"] = report_id
        captured["actor"] = actor
        return SimpleNamespace(
            id=report_id,
            title="Q1 Report",
            content="report body",
            format="markdown",
            source_thread_id="thread_1",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    fake_service = SimpleNamespace(get_report_for_actor=_fake_get_report_for_actor)

    monkeypatch.setattr(report_tool, "agent_tool_db_session", _fake_agent_tool_db_session)
    monkeypatch.setattr(report_tool.ReportService, "create", lambda tenant_id, db_session: fake_service)

    result = await report_tool.get_report.ainvoke({"report_id": 9}, config=runnable_config)
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert captured["report_id"] == 9
    assert captured["actor"].user_id == 123
    assert payload["report_id"] == 9
    assert payload["title"] == "Q1 Report"
    assert payload["content"] == "report body"
    assert payload["report_url"] == "/reports/9"


@pytest.mark.asyncio
async def test_update_report_tool_calls_service_with_owner(monkeypatch, runnable_config):
    captured: dict = {}

    async def _fake_update_report_for_actor(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            id=kwargs["report_id"],
            title=kwargs.get("title") or "Updated title",
            format=kwargs.get("format") or "markdown",
            updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

    fake_service = SimpleNamespace(update_report_for_actor=_fake_update_report_for_actor)

    monkeypatch.setattr(report_tool, "agent_tool_db_session", _fake_agent_tool_db_session)
    monkeypatch.setattr(report_tool.ReportService, "create", lambda tenant_id, db_session: fake_service)

    result = await report_tool.update_report.ainvoke(
        {
            "report_id": 11,
            "content": "new report content",
            "title": "New report title",
            "format": "html",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)

    assert result.status == ToolResultStatus.SUCCESS
    assert captured["report_id"] == 11
    assert captured["actor"].user_id == 123
    assert captured["content"] == "new report content"
    assert captured["report_metadata"]["length"] == len("new report content")
    assert payload["report_id"] == 11
    assert payload["report_url"] == "/reports/11"
