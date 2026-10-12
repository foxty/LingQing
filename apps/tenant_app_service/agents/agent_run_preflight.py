"""Preflight checks before scheduling or running agent workloads."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import ValidationError
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ
from apps.shared.tasks.domain import normalize_agent_run_task_config, parse_agent_run_task_config
from apps.tenant_app_service.agent_catalog.domain import SYSTEM_AGENT_ONE_ID
from apps.tenant_app_service.agent_catalog.services import AgentCatalogService


async def preflight_agent_run(
    db: AsyncSession,
    *,
    tenant_id: int,
    actor: ActorContext,
    agent_id: int,
) -> None:
    """Ensure the actor may invoke the agent (same gate as chat).

    Resource reads at run time use user ACL ∩ agent attachment IDs; partial attachment
    access is allowed for scheduled runs as for interactive chat.
    """
    if agent_id <= SYSTEM_AGENT_ONE_ID:
        return
    catalog = AgentCatalogService(tenant_id=tenant_id, db_session=db)
    await catalog.require_agent_access(
        agent_id=agent_id,
        actor=actor,
        action=ABAC_ACTION_READ,
    )


async def preflight_agent_run_task_config(
    db: AsyncSession,
    *,
    tenant_id: int,
    actor: ActorContext,
    task_config: dict[str, Any],
) -> None:
    """Validate agent_run task_config before create or update."""
    normalized = normalize_agent_run_task_config(task_config)
    try:
        parsed = parse_agent_run_task_config(normalized)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await preflight_agent_run(
        db,
        tenant_id=tenant_id,
        actor=actor,
        agent_id=parsed["agent_id"],
    )
