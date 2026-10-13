"""Build ``AgentLoadedConfig`` documents for catalog-backed (custom) agents."""

from __future__ import annotations

from typing import Any

from apps.tenant_app_service.agent_catalog.domain import CustomAgent
from apps.tenant_app_service.agents.domain import AgentLoadedConfig
from apps.tenant_app_service.agents.platform_tools import resolve_tool_defs
from apps.tenant_app_service.agents.system_agent_config import AgentConfigLoader

_RUNTIME_DEFAULT_KEYS = (
    "max_loop_iterations",
    "max_tokens",
    "temperature",
    "top_p",
    "frequency_penalty",
)

PROMPT_MODE_PLATFORM = "platform"


def runtime_defaults_from_system_agent(agent_def: dict[str, Any]) -> dict[str, Any]:
    """Pick loop/model defaults from a system agent YAML document."""
    return {key: agent_def[key] for key in _RUNTIME_DEFAULT_KEYS if key in agent_def}


def build_custom_agent_loaded_config(
    *,
    domain: CustomAgent,
    derived_tool_names: list[str],
    loader: AgentConfigLoader,
    runtime_defaults: dict[str, Any],
) -> AgentLoadedConfig:
    """Materialize a custom agent document without merging the full Agent One YAML blob."""
    platform_specs = loader.get_platform_tool_specs()
    document: AgentLoadedConfig = {
        "agent_id": domain.id,
        "name": domain.name,
        "system_prompt": domain.system_prompt,
        "default_tools": resolve_tool_defs(derived_tool_names, platform_specs),
        "example_questions": list(domain.example_questions),
        "prompt_mode": PROMPT_MODE_PLATFORM,
    }
    for key, value in runtime_defaults.items():
        document[key] = value  # type: ignore[literal-required]
    if domain.profile.model_profile_id is not None:
        document["model_profile_id"] = domain.profile.model_profile_id
    return document
