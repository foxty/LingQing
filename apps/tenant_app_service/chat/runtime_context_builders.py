"""Map chat/API types to agent runtime domain (outer layer)."""

from __future__ import annotations

from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.domain import (
    AgentCapabilityProfile,
    AgentRuntimeContext,
    AgentTenantContext,
    AgentUserContext,
)


def create_agent_runtime_user_context(user: UserDTO, access_token: str | None = None) -> AgentUserContext:
    return AgentUserContext(
        user_id=user.id,
        username=user.username,
        role=user.role,
        tenant_id=user.tenant_id,
        tenant_name=user.tenant_name,
        timezone_iana=user.timezone_iana,
        access_token=access_token,
    )


def create_agent_runtime_tenant_context(
    tenant_id: int,
    tenant_name: str,
    config: dict[str, object],
) -> AgentTenantContext:
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
    return AgentRuntimeContext(
        tenant=tenant_context,
        user=user_context,
        agent_id=agent_id,
        agent_name=agent_name,
        thread_id=thread_id,
        session_id=session_id,
        capability_profile=capability_profile,
    )
