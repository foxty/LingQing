"""Integration tests for custom-agent platform capabilities vs runtime tool allowlists."""

from __future__ import annotations

import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.policy_seed import seed_default_policies
from apps.shared.db.models import Agent, Tenant, User
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO
from apps.tenant_app_service.agents.runtime_capability import build_agent_capability_profile
from apps.tenant_app_service.chat.turn_service import ChatTurnService
from apps.tenant_app_service.agent_catalog.adapters import resolve_assignable_skills
from apps.tenant_app_service.skills.resolution import get_default_skill_resolver, reset_default_skill_resolver

from tests.conftest import project_root

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _sync_repo_builtin_skills_to_data_root():
    """Resolver reads ``EnvConfig.DATA_ROOT_PATH/skills``, not repo ``config/skills``."""
    from apps.config import EnvConfig

    data_root = Path(EnvConfig.DATA_ROOT_PATH or os.environ["DATA_ROOT_PATH"])
    skills_dst = data_root / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(project_root / "config" / "skills", skills_dst, dirs_exist_ok=True)
    reset_default_skill_resolver()
    get_default_skill_resolver().clear_cache()
    yield
    get_default_skill_resolver().clear_cache()


@pytest.mark.asyncio
async def test_task_scheduler_skill_agent_excludes_workspace_tools(async_db_session: AsyncSession):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"cap-{suffix}", slug=f"cap-{suffix}", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()
    await seed_default_policies(async_db_session, tenant.id)

    user = User(
        username=f"owner-{suffix}@example.com",
        email=f"owner-{suffix}@example.com",
        hashed_password="test",
        role="admin",
        tenant_id=tenant.id,
        status="active",
    )
    async_db_session.add(user)
    await async_db_session.flush()

    agent = Agent(
        tenant_id=tenant.id,
        owner_id=user.id,
        name=f"scheduler-{suffix}",
        description="scheduling only",
        system_prompt="Run schedules.",
        config={
            "platform_capabilities": [],
            "default_tools": [],
            "skills": ["task-scheduler"],
            "knowledge_base_ids": [],
            "data_source_ids": [],
            "api_connector_ids": [],
        },
        tags=[],
        example_questions=[],
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    async_db_session.add(agent)
    await async_db_session.commit()

    actor = ActorContext(tenant_id=tenant.id, user_id=user.id, user_role=user.role)
    assignable = resolve_assignable_skills(tenant_id=tenant.id, user_id=user.id)
    scheduler = next((skill for skill in assignable if skill.name == "task-scheduler"), None)
    assert scheduler is not None, "task-scheduler builtin skill must be on DATA_ROOT/skills for this test"
    assert "list_scheduled_tasks" in scheduler.tools

    profile = await build_agent_capability_profile(
        async_db_session,
        tenant_id=tenant.id,
        actor=actor,
        agent_id=agent.id,
    )
    assert profile is not None
    allowed = set(profile.allowed_tool_names or [])
    assert "run_bash_script" not in allowed
    assert "create_report" not in allowed
    assert "task-scheduler" in set(profile.allowed_skill_names or [])
    assert "list_scheduled_tasks" in allowed
    assert "schedule_task" in allowed


@pytest.mark.asyncio
async def test_get_agent_graph_custom_agent_passes_spec_tool_limits(async_db_session: AsyncSession, monkeypatch):
    suffix = uuid4().hex[:8]
    tenant = Tenant(name=f"graph-{suffix}", slug=f"graph-{suffix}", status="active")
    async_db_session.add(tenant)
    await async_db_session.flush()
    await seed_default_policies(async_db_session, tenant.id)

    user = User(
        username=f"admin-{suffix}@example.com",
        email=f"admin-{suffix}@example.com",
        hashed_password="test",
        role="admin",
        tenant_id=tenant.id,
        status="active",
    )
    async_db_session.add(user)
    await async_db_session.flush()

    agent = Agent(
        tenant_id=tenant.id,
        owner_id=user.id,
        name=f"kb-{suffix}",
        description="kb agent",
        system_prompt="Search docs.",
        config={
            "platform_capabilities": [],
            "skills": [],
            "knowledge_base_ids": [999001],
            "data_source_ids": [],
            "api_connector_ids": [],
        },
        tags=[],
        example_questions=[],
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    async_db_session.add(agent)
    await async_db_session.commit()

    captured: dict = {}

    async def capture_get_or_create(config, *, cache_revision=None, config_overrides=None):
        captured["config"] = config
        return object()

    service = ChatTurnService(tenant_id=tenant.id, db=async_db_session)
    monkeypatch.setattr(service.agent_pool, "get_or_create_agent", capture_get_or_create)

    current_user = UserDTO(
        id=user.id,
        username=user.username,
        role=user.role,
        tenant_id=tenant.id,
        tenant_name=tenant.name,
    )
    _graph, capability = await service._get_agent_graph(agent.id, current_user=current_user)

    assert capability is not None
    assert "search_documents" in capability.allowed_tool_names
    preloaded = captured["config"]
    assert preloaded["agent_id"] == agent.id
    assert "tags" not in preloaded
    limits = {item["name"]: item for item in preloaded["default_tools"]}
    assert limits["search_documents"]["limit"] == 5
