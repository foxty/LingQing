"""Domain models for custom agent catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.shared.domain.base_domain_model import BaseDomainModel

SYSTEM_AGENT_ONE_ID = -1
SYSTEM_AGENT_ONE_NAME = "Agent One"

CORE_SKILL_TOOLS = ("load_skill", "unload_skill", "read_skill_file")
KNOWLEDGE_TOOLS = ("search_documents", "retrieve_resource_context")
DATA_SOURCE_TOOLS = ("list_data_sources", "search_data_assets", "retrieve_resource_context")
API_CONNECTOR_TOOLS = ("search_apis", "retrieve_resource_context", "api_connector")
SHAREABLE_SKILL_SCOPES = frozenset({"builtin", "tenant"})
PERSONAL_SKILL_SCOPE = "personal"


@dataclass(frozen=True)
class AssignableSkill:
    """Skill snapshot supplied by the skills boundary. No skills-module types."""

    name: str
    description: str = ""
    scope: str = "builtin"
    tools: tuple[str, ...] = ()

    @property
    def is_shareable(self) -> bool:
        return self.scope in SHAREABLE_SKILL_SCOPES


def derive_tool_names(
    *,
    skills: list[str],
    knowledge_base_ids: list[int],
    data_source_ids: list[int],
    api_connector_ids: list[int],
) -> list[str]:
    """Always-on tools from assigned skills and attached resources.

    Skill-declared tools are not included; they attach on ``load_skill``.
    """
    names: list[str] = []
    seen: set[str] = set()

    def _add(name: str) -> None:
        if not name or name in seen:
            return
        seen.add(name)
        names.append(name)

    if skills:
        for name in CORE_SKILL_TOOLS:
            _add(name)
    if knowledge_base_ids:
        for name in KNOWLEDGE_TOOLS:
            _add(name)
    if data_source_ids:
        for name in DATA_SOURCE_TOOLS:
            _add(name)
    if api_connector_ids:
        for name in API_CONNECTOR_TOOLS:
            _add(name)
    return names


@dataclass
class AgentCapabilityProfile(BaseDomainModel):
    """Allowlist of capabilities a custom agent may use."""

    default_tools: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    knowledge_base_ids: list[int] = field(default_factory=list)
    data_source_ids: list[int] = field(default_factory=list)
    api_connector_ids: list[int] = field(default_factory=list)
    model_key: str | None = None

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> AgentCapabilityProfile:
        raw = config or {}
        return cls(
            default_tools=_as_str_list(raw.get("default_tools")),
            skills=_as_str_list(raw.get("skills")),
            knowledge_base_ids=_as_int_list(raw.get("knowledge_base_ids")),
            data_source_ids=_as_int_list(raw.get("data_source_ids")),
            api_connector_ids=_as_int_list(raw.get("api_connector_ids")),
            model_key=raw.get("model_key"),
        )

    def to_config(self) -> dict[str, Any]:
        return {
            "default_tools": list(self.default_tools),
            "skills": list(self.skills),
            "knowledge_base_ids": list(self.knowledge_base_ids),
            "data_source_ids": list(self.data_source_ids),
            "api_connector_ids": list(self.api_connector_ids),
            "model_key": self.model_key,
        }


@dataclass
class CustomAgent(BaseDomainModel):
    """User-created agent with an explicit capability allowlist."""

    id: int
    tenant_id: int
    owner_id: int
    name: str
    description: str | None
    system_prompt: str
    profile: AgentCapabilityProfile
    tags: list[str]
    example_questions: list[str]
    status: str
    created_at: datetime
    updated_at: datetime

    def is_active(self) -> bool:
        return self.status == "active"


def _as_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _as_int_list(value: Any) -> list[int]:
    if not value:
        return []
    ids: list[int] = []
    seen: set[int] = set()
    for item in value if isinstance(value, list) else [value]:
        try:
            parsed = int(item)
        except (TypeError, ValueError):
            continue
        if parsed in seen:
            continue
        seen.add(parsed)
        ids.append(parsed)
    return ids
