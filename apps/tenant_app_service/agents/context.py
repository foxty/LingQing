"""Agent execution context adapters and converters.

This module provides adapter functions to convert between API layer models
and domain models. It keeps the domain models (AgentUserContext, AgentRuntimeContext)
isolated from API dependencies.
"""

from langchain_core.runnables import RunnableConfig

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.domain import (
    AgentCapabilityProfile,
    AgentRuntimeContext,
    AgentTenantContext,
    AgentUserContext,
)


def delegated_data_source_ids(profile: AgentCapabilityProfile | None) -> list[int] | None:
    return None if profile is None else profile.delegated(profile.allowed_data_source_ids)


def delegated_api_connector_ids(profile: AgentCapabilityProfile | None) -> list[int] | None:
    return None if profile is None else profile.delegated(profile.allowed_api_connector_ids)


def extract_runtime_context(config: RunnableConfig) -> AgentRuntimeContext:
    """Extract runtime context from LangGraph config.

    This is a common helper to consistently access runtime context across
    all tools and agent nodes. Returns a typed AgentRuntimeContext object
    for better type safety and IDE support.

    Args:
        config: Runtime configuration (auto-injected by LangGraph)

    Returns:
        AgentRuntimeContext object with user, agent, and session contexts.

    Raises:
        ValueError: If config or runtime context is missing

    Example:
        runtime = extract_runtime_context(config)
        tenant_id = runtime.user.tenant_id
        agent_name = runtime.agent_name
        user_role = runtime.user.role
        session_id = runtime.session_id
    """
    if not config:
        raise ValueError("RunnableConfig is required for this Agent!")
    runtime_dict = config.get("configurable", {}).get("runtime", {})
    if not runtime_dict:
        raise ValueError("Runtime context is missing in RunnableConfig")
    return AgentRuntimeContext.model_validate(runtime_dict)


def create_agent_runtime_user_context(user: UserDTO, access_token: str | None = None) -> AgentUserContext:
    """Convert API User to AgentUserContext.

    Args:
        user: API layer User model

    Returns:
        AgentUserContext for agent execution
    """
    return AgentUserContext(
        user_id=user.id,
        username=user.username,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_name=user.tenant_name,
        timezone_iana=user.timezone_iana,
        access_token=access_token,
    )


def create_agent_runtime_tenant_context(tenant_id: int, tenant_name: str, config: dict[str, any]) -> AgentTenantContext:
    """Create AgentTenantContext from tenant information.

    Args:
        tenant_id: Tenant ID
        tenant_name: Tenant name
        config: Tenant-specific agent configuration
    Returns:
        AgentTenantContext for agent execution
    """
    return AgentTenantContext(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        config=config,
    )


def create_agent_runtime_context(
    tenant_context: AgentTenantContext,
    user_context: AgentUserContext,
    agent_id: int,
    agent_name: str,
    thread_id: str,
    session_id: str,
    capability_profile: AgentCapabilityProfile | None = None,
) -> AgentRuntimeContext:
    """Create AgentRuntimeContext from user and agent config.

    Args:
        user: API layer User model
        agent_config: Agent configuration
        thread_id: Conversation thread ID
        session_id: Unique session ID for this invocation

    Returns:
        AgentRuntimeContext for agent execution
    """
    return AgentRuntimeContext(
        tenant=tenant_context,
        user=user_context,
        agent_id=agent_id,
        agent_name=agent_name,
        thread_id=thread_id,
        session_id=session_id,
        capability_profile=capability_profile,
    )


def create_thread_id(user_id: int, tenant_id: int, agent_id: int) -> str:
    """Create thread ID for conversation persistence.

    Thread ID format: tenant_id_user_id_agent_id
    This ensures each user has a separate conversation thread with each agent.

    Args:
        user_id: User ID
        tenant_id: Tenant ID
        agent_id: Agent ID

    Returns:
        Thread ID string
    """
    return f"{tenant_id}_{user_id}_{agent_id}"


__all__ = [
    "AgentUserContext",
    "AgentRuntimeContext",
    "extract_runtime_context",
    "create_agent_runtime_user_context",
    "create_agent_runtime_context",
    "create_thread_id",
]
