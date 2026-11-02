"""Stub LLM on real AgentBase graphs for committed chat runtime integration tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.config import get_config

from apps.tenant_app_service.agents.agent_base import AgentBase


def patch_agent_base_stub_llm(
    monkeypatch: Any,
    *,
    content: str = "integration-stub-reply",
    on_llm_call: Callable[..., Awaitable[dict]] | None = None,
) -> None:
    """Replace ``AgentBase._llm_call`` so ``ChatTurnService`` runs the real LangGraph harness."""

    async def _stub_llm(
        self: AgentBase,
        state: dict,
        config: RunnableConfig | None = None,
    ) -> dict:
        if on_llm_call is not None:
            return await on_llm_call(self, state, config)
        from apps.tenant_app_service.agents.context import extract_runtime_context

        effective = config if config is not None else get_config()
        runtime = extract_runtime_context(effective)
        current = list(state.get("messages", []))
        current.append(
            AIMessage(
                id=str(uuid4()),
                content=content,
                additional_kwargs={"session_id": runtime.session_id},
            )
        )
        return {
            "messages": current,
            "loop_count": state.get("loop_count", 0) + 1,
        }

    monkeypatch.setattr(AgentBase, "_llm_call", _stub_llm)
    _clear_agent_pool()


def _clear_agent_pool() -> None:
    """Drop cached compiled graphs so stubs apply on the next turn."""
    from apps.tenant_app_service.agent_pool import get_agent_pool

    get_agent_pool()._pool.clear()


def patch_turn_session_end_noop(monkeypatch: Any) -> None:
    from apps.tenant_app_service.chat.turn_service import ChatTurnService

    monkeypatch.setattr(
        ChatTurnService,
        "schedule_session_end",
        lambda self, *args, **kwargs: None,
    )
