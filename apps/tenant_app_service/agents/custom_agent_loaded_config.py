"""Build ``AgentLoadedConfig`` documents for catalog-backed (custom) agents."""

from __future__ import annotations

from typing import Any

from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID, CustomAgent
from apps.tenant_app_service.agents.agent_config import DEFAULT_MAX_LOOP_ITERATIONS
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


def platform_runtime_defaults(loader: AgentConfigLoader) -> dict[str, Any]:
    """Platform fallback runtime fields (Agent One YAML). Custom agents use profile first."""
    agent_def = loader.get_system_agent_config(SYSTEM_AGENT_ONE_ID, materialize=False) or {}
    return runtime_defaults_from_system_agent(agent_def)


def resolve_max_loop_iterations(
    profile_max_loop: int | None,
    platform_defaults: dict[str, Any],
) -> int:
    """Profile wins, then Agent One YAML, then code default."""
    if profile_max_loop is not None:
        return profile_max_loop
    if "max_loop_iterations" in platform_defaults:
        return int(platform_defaults["max_loop_iterations"])
    return DEFAULT_MAX_LOOP_ITERATIONS


def resolved_max_loop_iterations(
    profile_max_loop: int | None,
    loader: AgentConfigLoader,
) -> int:
    """Single entry for graph load and catalog API (profile + platform YAML + code default)."""
    return resolve_max_loop_iterations(profile_max_loop, platform_runtime_defaults(loader))


def build_custom_agent_loaded_config(
    *,
    domain: CustomAgent,
    derived_tool_names: list[str],
    loader: AgentConfigLoader,
) -> AgentLoadedConfig:
    """Materialize a custom agent document without merging the full Agent One YAML blob."""
    platform_defaults = platform_runtime_defaults(loader)
    platform_specs = loader.get_platform_tool_specs()
    document: AgentLoadedConfig = {
        "agent_id": domain.id,
        "name": domain.name,
        "system_prompt": domain.system_prompt,
        "default_tools": resolve_tool_defs(derived_tool_names, platform_specs),
        "example_questions": list(domain.example_questions),
        "prompt_mode": PROMPT_MODE_PLATFORM,
        "max_loop_iterations": resolved_max_loop_iterations(
            domain.profile.max_loop_iterations,
            loader,
        ),
    }
    for key, value in platform_defaults.items():
        if key == "max_loop_iterations":
            continue
        document[key] = value  # type: ignore[literal-required]
    if domain.profile.model_profile_id is not None:
        document["model_profile_id"] = domain.profile.model_profile_id
    return document