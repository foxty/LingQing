"""Domain models for agents.

Domain models are framework-agnostic and represent pure business entities.
"""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, NamedTuple, TypedDict

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

from apps.shared.domain.base_domain_model import BaseDomainModel
from apps.tenant_app_service.skills.domain import SkillLocator, SkillType

# Back-compat alias: SkillScope and SkillType share the same value space
# (builtin/tenant/personal). Existing imports of ``SkillScope`` continue
# to work; new code should prefer ``SkillType`` from
# ``apps.tenant_app_service.skills.domain``.
SkillScope = SkillType
__all__ = [
    "AgentCapabilityProfile",
    "AgentLoadedConfig",
    "AgentRuntimeContext",
    "AgentTenantContext",
    "AgentToolYaml",
    "AgentUserContext",
    "SkillConfig",
    "SkillLocator",
    "SkillScope",
    "SkillState",
    "SkillType",
    "ToolConfig",
    "ToolExecResult",
    "PromptContextStats",
]

RETENTION_TRANSIENT: Literal["transient"] = "transient"
RETENTION_LONG_LIVED: Literal["long_lived"] = "long_lived"
ResultRetention = Literal["transient", "long_lived"]

TOOL_LIMIT_UNLIMITED = 2**31 - 1

ToolCallCounts = dict[str, int]
ToolCache = dict[str, str]


class AgentToolYaml(TypedDict, total=False):
    """One tool entry in an ``agents.yaml`` / preloaded agent document."""

    name: str
    limit: int
    hitl: dict[str, Any]
    result_retention: str
    cacheable: bool
    cache_invalidates: list[str]


class AgentLoadedConfig(TypedDict, total=False):
    """Resolved agent document consumed by ``AgentConfig`` / ``AgentBase``.

    System vs custom is only where this document came from (YAML vs catalog overlay).
    ``agent_id`` is a field on the document, not a lookup key for the graph class.
    """

    agent_id: int
    name: str
    system_prompt: str
    default_tools: list[AgentToolYaml]
    example_questions: list[str]
    model_key: str
    temperature: float
    top_p: float
    max_tokens: int
    frequency_penalty: float
    max_loop_iterations: int
    classification: Any
    response_format: Any


class ToolExecResult(NamedTuple):
    message: ToolMessage
    tool_call_counts: ToolCallCounts
    tool_cache: ToolCache


@dataclass
class PromptContextStats(BaseDomainModel):
    """Observability stats for prompt context preprocessing stages."""

    original_count: int = 0  # Conversation message count before any preprocessing.
    sanitized_count: int = 0  # Messages removed by sanitize (invalid tool-call/tool-result state).
    sanitized_chars: int = 0  # Character volume removed during sanitize.
    trimmed_count: int = 0  # Messages removed by window trimming.
    trimmed_chars: int = 0  # Character volume removed by trimming.
    preserved_long_lived: int = 0  # Long-lived ToolMessages preserved from dropped groups.
    preserved_chars: int = 0  # Character volume preserved from long-lived tool outputs.
    compressed_transient: int = 0  # Transient ToolMessages truncated in kept history.
    compressed_chars_saved: int = 0  # Character volume saved by truncating transient outputs.
    final_count: int = 0  # Final message count sent to LLM (includes system messages).


@dataclass
class ToolConfig(BaseDomainModel):
    """Tool configuration used across YAML loading, resolver merging, and runtime execution.

    When loaded from YAML, ``tool`` is None. After registry resolution it is bound
    to the actual BaseTool instance.
    """

    name: str
    limit: int = TOOL_LIMIT_UNLIMITED
    hitl: dict[str, Any] = field(default_factory=dict)
    result_retention: ResultRetention = RETENTION_TRANSIENT
    cacheable: bool = False
    cache_invalidates: list[str] = field(default_factory=list)
    tool: BaseTool | None = field(default=None, repr=False)

    @property
    def hitl_mode(self) -> str:
        return self.hitl.get("mode", "never")


@dataclass
class SkillConfig(BaseDomainModel):
    """Configuration for one skill definition file."""

    name: str
    system_prompt: str
    description: str = ""
    tools: list[ToolConfig] = field(default_factory=list)
    api_refs: list[str] = field(default_factory=list)
    source_file: str = ""
    source_format: str = "legacy_yaml"
    skill_metadata: dict[str, str] = field(default_factory=dict)
    scope: SkillScope = SkillScope.BUILTIN
    locator: SkillLocator | None = None


@dataclass
class SkillState(BaseDomainModel):
    """Skill-related state fields for AgentState."""

    skill_switch_loop: int  # Loop # when skill state changed
    loaded_skills: list[str] = field(default_factory=list)  # Active skill list (ordered)
    skill_history: list[dict[str, Any]] = field(default_factory=list)  # Audit trail: [{action, loaded_skills, ...}]


@dataclass
class AgentUserContext(BaseDomainModel):
    """User context for agent execution.

    Provides minimal user information needed by agent tools for:
    - Permission checks
    - Data filtering
    - Audit logging
    - Thread isolation
    """

    user_id: int
    username: str
    role: str
    tenant_id: int
    tenant_name: str
    timezone_iana: str | None = None
    access_token: str | None = None

    def model_dump(self) -> dict[str, Any]:
        """Convert to dict (Pydantic compatibility)."""
        return asdict(self)

    @classmethod
    def model_validate(cls, obj: dict[str, Any]) -> "AgentUserContext":
        """Create instance from dict (Pydantic compatibility)."""
        return cls(**obj)


@dataclass
class AgentTenantContext(BaseDomainModel):
    """Tenant context for agent execution.

    Provides minimal tenant information needed by agent tools for:
    - Permission checks
    - Data filtering
    - Audit logging
    """

    tenant_id: int
    tenant_name: str
    config: dict[str, Any]  # Tenant-specific agent config

    def model_dump(self) -> dict[str, Any]:
        """Convert to dict (Pydantic compatibility)."""
        return asdict(self)

    @classmethod
    def model_validate(cls, obj: dict[str, Any]) -> "AgentTenantContext":
        """Create instance from dict (Pydantic compatibility)."""
        return cls(**obj)


@dataclass
class AgentCapabilityProfile(BaseDomainModel):
    """Runtime allowlist for a custom agent. Unset fields mean unrestricted."""

    allowed_tool_names: list[str] | None = None
    allowed_skill_names: list[str] | None = None
    allowed_collection_ids: list[int] | None = None
    allowed_data_source_ids: list[int] | None = None
    allowed_api_connector_ids: list[int] | None = None
    delegate: bool = False

    def delegated(self, attached_ids: list[int] | None) -> list[int] | None:
        """Attached resource IDs when this invoker may use the agent's datascope."""
        if not self.delegate:
            return None
        return list(attached_ids) if attached_ids else None

    @classmethod
    def model_validate(cls, obj: dict[str, Any] | None) -> "AgentCapabilityProfile | None":
        if obj is None:
            return None
        if isinstance(obj, cls):
            return obj
        return cls(**obj)


@dataclass
class AgentRuntimeContext(BaseDomainModel):
    """Runtime context for agent execution.

    Contains all necessary runtime information for tools:
    - User context (permissions, tenant)
    - Agent identity (from AgentConfig)
    - Thread/session IDs (for caching and tracking)
    """

    tenant: AgentTenantContext
    user: AgentUserContext
    agent_id: int
    agent_name: str
    thread_id: str
    session_id: str
    capability_profile: AgentCapabilityProfile | None = None

    @classmethod
    def model_validate(cls, obj: dict[str, Any]) -> "AgentRuntimeContext":
        """Create instance from dict (Pydantic compatibility)."""
        if isinstance(obj.get("user"), dict):
            user = AgentUserContext.model_validate(obj["user"])
        else:
            user = obj["user"]
        if isinstance(obj.get("tenant"), dict):
            tenant = AgentTenantContext.model_validate(obj["tenant"])
        else:
            tenant = obj["tenant"]
        profile = obj.get("capability_profile")
        return cls(
            tenant=tenant,
            user=user,
            agent_id=obj["agent_id"],
            agent_name=obj["agent_name"],
            thread_id=obj["thread_id"],
            session_id=obj["session_id"],
            capability_profile=AgentCapabilityProfile.model_validate(profile) if profile else None,
        )
