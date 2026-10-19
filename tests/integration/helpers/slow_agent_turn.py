"""Stub LangGraph invoke for in-flight / overlapping chat admission tests."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage


def patch_in_flight_agent_graph(
    monkeypatch: Any,
    *,
    in_flight: asyncio.Event,
    release: asyncio.Event,
) -> None:
    """Hold ``complete_chat_turn`` until ``release`` is set; signal ``in_flight`` when held."""

    class _SlowGraph:
        def get_name(self) -> str:
            return "SlowAgent"

        async def ainvoke(self, input_state: dict, config: dict) -> dict:
            in_flight.set()
            await release.wait()
            messages = list(input_state.get("messages", []))
            messages.append(AIMessage(content="slow-turn-done"))
            return {
                "messages": messages,
                "loop_count": 0,
                "tool_call_counts": {},
            }

    async def fake_get_agent_graph(self, agent_id, current_user):
        return _SlowGraph(), None

    monkeypatch.setattr(
        "apps.tenant_app_service.chat.turn_service.ChatTurnService._get_agent_graph",
        fake_get_agent_graph,
    )
    monkeypatch.setattr(
        "apps.tenant_app_service.chat.turn_service.ChatTurnService.create_thread_title_if_1st_message",
        AsyncMock(return_value=None),
    )


def patch_fast_agent_graph(monkeypatch: Any) -> None:
    """Instant stub reply (no LLM) for racing admission tests."""
    from tests.slack.chat_turn_mock import patch_slack_chat_turn_complete_only

    patch_slack_chat_turn_complete_only(monkeypatch)
