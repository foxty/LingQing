"""Regression tests for chat ↔ agent module boundary after port refactor."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.agents.agent_base import AgentBase

_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENTS_PKG = _REPO_ROOT / "apps" / "tenant_app_service" / "agents"


def _python_files_under_agents() -> list[Path]:
    return [p for p in _AGENTS_PKG.rglob("*.py") if p.is_file()]


def _imports_chat_module(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("apps.tenant_app_service.chat"):
                hits.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("apps.tenant_app_service.chat"):
                    hits.append(alias.name)
    return hits


def test_agents_package_does_not_import_chat():
    violations: list[str] = []
    for path in _python_files_under_agents():
        for mod in _imports_chat_module(path):
            violations.append(f"{path.relative_to(_REPO_ROOT)} imports {mod}")
    assert violations == []


@pytest.fixture
def agent(agent_stub_config_factory, runtime_context):
    stub_config = agent_stub_config_factory(
        agent_id=runtime_context.agent_id,
        agent_name=runtime_context.agent_name,
        system_prompt="test prompt",
    )
    return AgentBase(stub_config)


@pytest.mark.asyncio
async def test_load_history_requires_run_context_port(agent, runtime_context):
    run_id = str(uuid4())
    state = {"messages": [HumanMessage(id="h1", content="hello")]}
    config = RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
            "session_id": runtime_context.session_id,
            "run_id": run_id,
            "db_session": AsyncMock(),
        }
    )
    with pytest.raises(ValidationError, match="run_context_port"):
        await agent._load_history(state, config)


@pytest.mark.asyncio
async def test_load_history_skip_flag_does_not_require_memory(agent, runtime_context):
    state = {"messages": [HumanMessage(id="h1", content="hello")]}
    config = RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
            "session_id": runtime_context.session_id,
            "skip_load_history": True,
        }
    )
    assert await agent._load_history(state, config) == {}


@pytest.mark.asyncio
async def test_load_history_delegates_to_port(agent, runtime_context):
    run_id = str(uuid4())
    expected = [HumanMessage(id="hist", content="prior")]
    memory = AsyncMock()
    memory.load_prompt_context.return_value = expected
    state = {"messages": [HumanMessage(id="h1", content="hello")]}
    config = RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
            "session_id": runtime_context.session_id,
            "run_id": run_id,
            "db_session": AsyncMock(),
            "run_context_port": memory,
        }
    )
    with patch(
        "apps.tenant_app_service.hitl.history.hydrate_hitl_history_messages",
        new=AsyncMock(side_effect=lambda msgs, **_: msgs),
    ):
        update = await agent._load_history(state, config)

    memory.load_prompt_context.assert_awaited_once()
    merged = update["messages"]
    assert merged[0].id == "hist"
    assert merged[-1].id == "h1"


@pytest.mark.asyncio
async def test_persist_run_messages_requires_run_context_port(agent, runtime_context):
    config = RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
            "session_id": runtime_context.session_id,
            "run_id": str(uuid4()),
        }
    )
    with pytest.raises(ValidationError, match="run_context_port"):
        await agent._persist_run_messages({"messages": []}, config)
