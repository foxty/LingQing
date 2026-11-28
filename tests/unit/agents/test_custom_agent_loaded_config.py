"""Tests for custom agent loaded config construction."""

from datetime import UTC, datetime

import pytest
import yaml

from apps.tenant_app_service.agent_catalog.domain import AgentCapabilityProfile, CustomAgent
from apps.tenant_app_service.agents.agent_config import DEFAULT_MAX_LOOP_ITERATIONS
from apps.tenant_app_service.agents.custom_agent_loaded_config import (
    build_custom_agent_loaded_config,
    platform_runtime_defaults,
    resolve_max_loop_iterations,
    resolved_max_loop_iterations,
    runtime_defaults_from_system_agent,
)
from apps.tenant_app_service.agents.system_agent_config import AgentConfigLoader


def _custom_agent(**overrides):
    profile = overrides.pop("profile", AgentCapabilityProfile(skills=["data_analyst"]))
    now = datetime.now(UTC)
    base = CustomAgent(
        id=42,
        tenant_id=1,
        owner_id=1,
        name="HR Bot",
        description=None,
        system_prompt="You help with HR policies.",
        profile=profile,
        tags=[],
        example_questions=["Question?"],
        status="active",
        created_at=now,
        updated_at=now,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_runtime_defaults_from_system_agent_picks_known_keys():
    defaults = runtime_defaults_from_system_agent(
        {"max_loop_iterations": 40, "max_tokens": 4096, "name": "Agent One", "tags": ["x"]}
    )
    assert defaults == {"max_loop_iterations": 40, "max_tokens": 4096}


def test_resolved_max_loop_iterations_uses_loader(tmp_path):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "platform": {"tool_specs": {}},
                "system_agents": {"agent_one": {"agent_id": -1, "max_loop_iterations": 44}},
                "mini_agents": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loader = AgentConfigLoader(config_path=str(agents_yaml))
    assert resolved_max_loop_iterations(None, loader) == 44
    assert resolved_max_loop_iterations(90, loader) == 90


def test_resolve_max_loop_iterations_profile_then_platform_then_code():
    assert resolve_max_loop_iterations(80, {"max_loop_iterations": 33}) == 80
    assert resolve_max_loop_iterations(None, {"max_loop_iterations": 33}) == 33
    assert resolve_max_loop_iterations(None, {}) == DEFAULT_MAX_LOOP_ITERATIONS


def test_build_custom_agent_loaded_config_uses_platform_specs(tmp_path):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "platform": {
                    "system_prompt_baseline": "Baseline rules",
                    "tool_specs": {"search_documents": {"limit": 5}},
                },
                "system_agents": {
                    "agent_one": {
                        "agent_id": -1,
                        "name": "Agent One",
                        "system_prompt": "Role",
                        "default_tools": ["search_documents"],
                        "max_loop_iterations": 33,
                    }
                },
                "mini_agents": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loader = AgentConfigLoader(config_path=str(agents_yaml))
    loader.get_platform_tool_specs()

    document = build_custom_agent_loaded_config(
        domain=_custom_agent(),
        derived_tool_names=["search_documents"],
        loader=loader,
    )

    assert document["agent_id"] == 42
    assert document["system_prompt"] == "You help with HR policies."
    assert document["prompt_mode"] == "platform"
    assert document["default_tools"] == [{"name": "search_documents", "limit": 5}]
    assert document["max_loop_iterations"] == 33
    assert "tags" not in document


def test_build_custom_agent_loaded_config_profile_overrides_platform_yaml(tmp_path):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "platform": {"tool_specs": {}},
                "system_agents": {
                    "agent_one": {
                        "agent_id": -1,
                        "name": "Agent One",
                        "system_prompt": "Role",
                        "default_tools": [],
                        "max_loop_iterations": 33,
                    }
                },
                "mini_agents": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loader = AgentConfigLoader(config_path=str(agents_yaml))
    profile = AgentCapabilityProfile(skills=["data_analyst"], max_loop_iterations=80)
    document = build_custom_agent_loaded_config(
        domain=_custom_agent(profile=profile),
        derived_tool_names=[],
        loader=loader,
    )
    assert document["max_loop_iterations"] == 80


def test_platform_runtime_defaults_reads_agent_one(tmp_path):
    agents_yaml = tmp_path / "agents.yaml"
    agents_yaml.write_text(
        yaml.safe_dump(
            {
                "platform": {"tool_specs": {}},
                "system_agents": {
                    "agent_one": {
                        "agent_id": -1,
                        "max_loop_iterations": 41,
                        "max_tokens": 3000,
                    }
                },
                "mini_agents": {},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loader = AgentConfigLoader(config_path=str(agents_yaml))
    assert platform_runtime_defaults(loader) == {"max_loop_iterations": 41, "max_tokens": 3000}