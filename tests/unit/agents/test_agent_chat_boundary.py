"""Regression tests for chat ↔ agent module boundary after port refactor."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.agents.agent_base import AgentBase

_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENTS_PKG = _REPO_ROOT / "apps" / "tenant_app_service" / "agents"

# Outward imports allowed until catalog/tenant are moved behind ports (tracked separately).
_OUTWARD_IMPORT_ALLOWLIST: dict[str, set[str]] = {
    "apps.tenant_app_service.agent_catalog": {
        "agents/custom_agent_loaded_config.py",
        "agents/runtime_capability.py",
        "agents/agent_run_preflight.py",
    },
    "apps.tenant_app_service.tenant": {
        "agents/mini_agent.py",
    },
    "apps.tenant_app_service.skills": {
        "agents/domain.py",
        "agents/agent_config.py",
        "agents/skills/loader.py",
        "agents/tools/bash_sandbox.py",
        "agents/tools/skill_reference.py",
    },
}


def _python_files_under_agents() -> list[Path]:
    return [p for p in _AGENTS_PKG.rglob("*.py") if p.is_file()]


def _forbidden_imports(path: Path, forbidden_prefixes: tuple[str, ...]) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    rel = path.relative_to(_REPO_ROOT / "apps" / "tenant_app_service").as_posix()
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
        elif isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        for mod in modules:
            for prefix in forbidden_prefixes:
                if not mod.startswith(prefix):
                    continue
                allowed = _OUTWARD_IMPORT_ALLOWLIST.get(prefix, set())
                if rel in allowed:
                    continue
                hits.append(f"{rel} imports {mod}")
    return hits


def test_agents_package_does_not_import_chat_or_hitl():
    forbidden = (
        "apps.tenant_app_service.chat",
        "apps.tenant_app_service.hitl",
    )
    violations: list[str] = []
    for path in _python_files_under_agents():
        violations.extend(_forbidden_imports(path, forbidden))
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
async def test_load_history_requires_agent_run_port(agent, runtime_context):
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
    with pytest.raises(ValidationError, match="agent_run_port"):
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
    port = AsyncMock()
    port.load_prompt_context.return_value = expected
    port.hydrate_prompt_messages = AsyncMock(side_effect=lambda msgs, **_: msgs)
    port.is_run_cancelled = AsyncMock(return_value=False)
    state = {"messages": [HumanMessage(id="h1", content="hello")]}
    config = RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
            "session_id": runtime_context.session_id,
            "run_id": run_id,
            "db_session": AsyncMock(),
            "agent_run_port": port,
        }
    )
    update = await agent._load_history(state, config)

    port.load_prompt_context.assert_awaited_once()
    port.hydrate_prompt_messages.assert_awaited_once()
    merged = update["messages"]
    assert merged[0].id == "hist"
    assert merged[-1].id == "h1"


@pytest.mark.asyncio
async def test_persist_run_messages_requires_agent_run_port(agent, runtime_context):
    config = RunnableConfig(
        configurable={
            "thread_id": runtime_context.thread_id,
            "runtime": runtime_context.model_dump(),
            "session_id": runtime_context.session_id,
            "run_id": str(uuid4()),
        }
    )
    with pytest.raises(ValidationError, match="agent_run_port"):
        await agent._persist_run_messages({"messages": []}, config)
