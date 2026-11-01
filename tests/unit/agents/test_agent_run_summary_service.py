"""Unit tests for in-run summary splicing. No database and no LLM."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from apps.tenant_app_service.agents.memory.agent_run_summary_service import (
    compact_prepared_messages,
    older_tool_round_prefix,
    splice_run_summary,
)


def test_older_tool_round_prefix_keeps_the_latest_round():
    first_ai = AIMessage(id="ai-1", content="search", tool_calls=[{"id": "c1", "name": "search", "args": {}}])
    first_tool = ToolMessage(id="tool-1", content="big", tool_call_id="c1")
    second_ai = AIMessage(id="ai-2", content="fetch", tool_calls=[{"id": "c2", "name": "fetch", "args": {}}])
    second_tool = ToolMessage(id="tool-2", content="fresh", tool_call_id="c2")

    prefix, tail = older_tool_round_prefix([first_ai, first_tool, second_ai, second_tool])

    assert [message.id for message in prefix] == ["ai-1", "tool-1"]
    assert [message.id for message in tail] == ["ai-2", "tool-2"]


def test_single_tool_round_is_not_a_prefix():
    ai = AIMessage(id="ai-1", content="search", tool_calls=[{"id": "c1", "name": "search", "args": {}}])
    tool = ToolMessage(id="tool-1", content="big", tool_call_id="c1")

    prefix, tail = older_tool_round_prefix([ai, tool])

    assert prefix == []
    assert [message.id for message in tail] == ["ai-1", "tool-1"]


def test_splice_drops_prefix_and_keeps_trigger_human():
    history = [
        SystemMessage(content="thread", additional_kwargs={"summary_type": "thread_summary"}),
        HumanMessage(id="old", content="old ask"),
        AIMessage(id="old-ai", content="old answer"),
        HumanMessage(id="trigger", content="current ask"),
    ]
    prefix_ai = AIMessage(id="ai-1", content="search", tool_calls=[{"id": "c1", "name": "search", "args": {}}])
    prefix_tool = ToolMessage(id="tool-1", content="big", tool_call_id="c1")
    tail_ai = AIMessage(id="ai-2", content="fetch", tool_calls=[{"id": "c2", "name": "fetch", "args": {}}])

    spliced = splice_run_summary(
        history + [prefix_ai, prefix_tool, tail_ai],
        summary_text="did the search",
        cutoff_message_id="tool-1",
    )

    assert spliced[3].content == "current ask"
    assert spliced[4].additional_kwargs["summary_type"] == "agent_run_summary"
    assert "did the search" in spliced[4].content
    assert [message.id for message in spliced[5:]] == ["ai-2"]


@pytest.mark.asyncio
async def test_existing_run_summary_is_spliced_when_under_budget(monkeypatch):
    existing = MagicMock()
    existing.summary_text = "did the search"
    existing.cutoff_message_id = "tool-1"
    repo = AsyncMock()
    repo.get_for_run.return_value = existing
    monkeypatch.setattr(
        "apps.tenant_app_service.chat.agent_run_summary_repository.AgentRunSummaryRepository",
        lambda db: repo,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.memory.agent_run_summary_service.count_tokens",
        lambda *args, **kwargs: 1,
    )

    human = HumanMessage(id="trigger", content="current ask")
    prefix_ai = AIMessage(id="ai-1", content="search", tool_calls=[{"id": "c1", "name": "search", "args": {}}])
    prefix_tool = ToolMessage(id="tool-1", content="big", tool_call_id="c1")
    tail_ai = AIMessage(id="ai-2", content="fetch", tool_calls=[{"id": "c2", "name": "fetch", "args": {}}])

    result = await compact_prepared_messages(
        [human, prefix_ai, prefix_tool, tail_ai],
        db=AsyncMock(),
        tenant_id=1,
        thread_id="thread-1",
        run_id="run-1",
        tools=[],
    )

    repo.upsert.assert_not_called()
    assert result[1].additional_kwargs["summary_type"] == "agent_run_summary"
    assert [message.id for message in result if getattr(message, "id", None)] == ["trigger", "ai-2"]


@pytest.mark.asyncio
async def test_over_budget_latest_tool_round_is_left_verbatim(monkeypatch):
    repo = AsyncMock()
    repo.get_for_run.return_value = None
    monkeypatch.setattr(
        "apps.tenant_app_service.chat.agent_run_summary_repository.AgentRunSummaryRepository",
        lambda db: repo,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.agents.memory.agent_run_summary_service.count_tokens",
        lambda *args, **kwargs: 10**9,
    )

    human = HumanMessage(id="trigger", content="current ask")
    ai = AIMessage(id="ai-1", content="search", tool_calls=[{"id": "c1", "name": "search", "args": {}}])
    tool = ToolMessage(id="tool-1", content="fresh", tool_call_id="c1")

    result = await compact_prepared_messages(
        [human, ai, tool],
        db=AsyncMock(),
        tenant_id=1,
        thread_id="thread-1",
        run_id="run-1",
        tools=[],
    )

    repo.upsert.assert_not_called()
    assert [message.id for message in result] == ["trigger", "ai-1", "tool-1"]
