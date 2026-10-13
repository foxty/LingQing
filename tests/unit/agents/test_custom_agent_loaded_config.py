"""Tests for custom agent loaded config construction."""

from datetime import UTC, datetime

import yaml

from apps.tenant_app_service.agent_catalog.domain import AgentCapabilityProfile, CustomAgent
from apps.tenant_app_service.agents.custom_agent_loaded_config import (
    build_custom_agent_loaded_config,
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
        runtime_defaults={"max_loop_iterations": 33},
    )

    assert document["agent_id"] == 42
    assert document["system_prompt"] == "You help with HR policies."
    assert document["prompt_mode"] == "platform"
    assert document["default_tools"] == [{"name": "search_documents", "limit": 5}]
    assert document["max_loop_iterations"] == 33
    assert "tags" not in document
