"""Unit tests for custom agent catalog authz and capability profiles."""

import pytest
from sqlalchemy import select

from apps.shared.authz.authz_query_builder import evaluate_resource_action
from apps.shared.authz.ta_permissions import TenantAppPermissions
from apps.shared.authz.ta_rbac import DEFAULT_ROLE_PERMISSIONS, ta_permission_implies
from apps.shared.core.exceptions import AuthorizationError, ValidationError
from apps.shared.core.policy_seed import seed_default_policies
from apps.shared.db.models import AclGrant, DocumentCollection, Tenant, User
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ, RESOURCE_TYPE_DOCUMENT_COLLECTION
from apps.tenant_app_service.agent_catalog.domain import (
    PERSONAL_SKILL_SCOPE,
    SYSTEM_AGENT_ONE_ID,
    AgentCapabilityProfile,
    AssignableSkill,
)
from apps.tenant_app_service.agent_catalog.dtos import AgentCapabilityConfigDTO, AgentCreateRequest
from apps.tenant_app_service.agent_catalog.services import AgentCatalogService
from apps.tenant_app_service.agents.agent_config import AgentConfig
from apps.tenant_app_service.agents.domain import (
    AgentCapabilityProfile as RuntimeProfile,
)
from apps.tenant_app_service.agents.domain import (
    AgentRuntimeContext,
    AgentTenantContext,
    AgentUserContext,
    SkillConfig,
)
from apps.tenant_app_service.skills.domain import SkillType


def test_derive_tool_names_from_skills_and_context():
    from apps.tenant_app_service.agent_catalog.domain import derive_tool_names

    assert (
        derive_tool_names(
            skills=[],
            knowledge_base_ids=[],
            data_source_ids=[],
            api_connector_ids=[],
        )
        == []
    )

    derived = derive_tool_names(
        skills=["data_analyst"],
        knowledge_base_ids=[12],
        data_source_ids=[],
        api_connector_ids=[],
    )
    assert derived[:3] == ["load_skill", "unload_skill", "read_skill_file"]
    assert "run_sql_query_on_datasource" not in derived
    assert "search_documents" in derived
    assert "retrieve_resource_context" in derived


def test_allowed_runtime_tool_names_includes_skill_tools(monkeypatch):
    from unittest.mock import MagicMock

    from apps.tenant_app_service.agent_catalog.services import AgentCatalogService

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_catalog.services.TOOL_REGISTRY",
        {
            "load_skill": object(),
            "unload_skill": object(),
            "read_skill_file": object(),
            "run_sql_query_on_datasource": object(),
        },
    )
    service = AgentCatalogService(tenant_id=1, db_session=MagicMock())
    profile = AgentCapabilityProfile(skills=["data_analyst"])
    skills = [AssignableSkill(name="data_analyst", tools=("run_sql_query_on_datasource",))]
    assert "run_sql_query_on_datasource" not in service.derived_tool_names(profile, assignable_skills=skills)
    allowed = service.allowed_runtime_tool_names(profile, assignable_skills=skills)
    assert "load_skill" in allowed
    assert "run_sql_query_on_datasource" in allowed


def test_capability_profile_parses_config():
    profile = AgentCapabilityProfile.from_config(
        {
            "default_tools": ["search_documents", "load_skill"],
            "skills": ["hr_policy"],
            "knowledge_base_ids": [1, "2", 2],
            "data_source_ids": [],
            "api_connector_ids": None,
        }
    )
    assert profile.default_tools == ["search_documents", "load_skill"]
    assert profile.skills == ["hr_policy"]
    assert profile.knowledge_base_ids == [1, 2]


@pytest.mark.asyncio
async def test_create_rejects_unreadable_collection(async_db_session, monkeypatch):
    tenant = Tenant(name="agent_cat", slug="agent_cat", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    owner = User(username="owner", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    other = User(username="other", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add_all([owner, other])
    await async_db_session.flush()
    await seed_default_policies(async_db_session, tenant.id)
    collection = DocumentCollection(
        tenant_id=tenant.id,
        name="secret-kb",
        description=None,
        owner_id=other.id,
    )
    async_db_session.add(collection)
    await async_db_session.commit()
    await async_db_session.refresh(owner)
    await async_db_session.refresh(collection)

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_catalog.services.TOOL_REGISTRY",
        {"search_documents": object()},
    )

    service = AgentCatalogService(tenant_id=tenant.id, db_session=async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="member")
    with pytest.raises(AuthorizationError):
        await service.create_agent(
            payload=AgentCreateRequest(
                name="HR Bot",
                system_prompt="help",
                config=AgentCapabilityConfigDTO(
                    default_tools=["search_documents"],
                    knowledge_base_ids=[collection.id],
                ),
            ),
            actor=actor,
        )


@pytest.mark.asyncio
async def test_member_can_create_and_other_cannot_read_without_share(async_db_session, monkeypatch):
    tenant = Tenant(name="agent_cat2", slug="agent_cat2", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    owner = User(username="owner2", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    peer = User(username="peer2", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add_all([owner, peer])
    await async_db_session.flush()
    await seed_default_policies(async_db_session, tenant.id)
    await async_db_session.commit()
    await async_db_session.refresh(owner)
    await async_db_session.refresh(peer)

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_catalog.services.TOOL_REGISTRY",
        {"search_documents": object()},
    )

    service = AgentCatalogService(tenant_id=tenant.id, db_session=async_db_session)
    created = await service.create_agent(
        payload=AgentCreateRequest(
            name="Ops Bot",
            system_prompt="ops",
            config=AgentCapabilityConfigDTO(default_tools=["search_documents"]),
        ),
        actor=ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="member"),
    )
    assert created.id > 0
    assert created.is_system is False

    listed = await service.list_agents_for_actor(
        actor=ActorContext(tenant_id=tenant.id, user_id=peer.id, user_role="member")
    )
    assert all(item.id != created.id for item in listed)
    assert any(item.id == SYSTEM_AGENT_ONE_ID for item in listed)

    with pytest.raises(AuthorizationError):
        await service.get_agent_for_actor(
            agent_id=created.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=peer.id, user_role="member"),
        )


def test_runtime_filters_skills_and_tools(monkeypatch):
    manager = AgentConfig(
        {
            "agent_id": -1,
            "name": "Test",
            "system_prompt": "hi",
            "default_tools": [{"name": "search_documents"}, {"name": "load_skill"}],
        },
    )

    class DummySkill:
        def __init__(self, name, scope):
            self.name = name
            self.scope = scope
            self.description = name
            self.tools = []

    monkeypatch.setattr(
        manager,
        "_skill_resolution",
        type(
            "R",
            (),
            {
                "resolve": staticmethod(
                    lambda **_k: {
                        "hr_policy": SkillConfig(
                            name="hr_policy",
                            system_prompt="hr",
                            description="hr",
                            scope=SkillType.TENANT,
                        ),
                        "secret": SkillConfig(
                            name="secret",
                            system_prompt="p",
                            description="p",
                            scope=SkillType.PERSONAL,
                        ),
                    }
                )
            },
        )(),
    )

    runtime = AgentRuntimeContext(
        tenant=AgentTenantContext(tenant_id=1, tenant_name="t", config={}),
        user=AgentUserContext(user_id=2, username="u", role="member", tenant_id=1, tenant_name="t"),
        agent_id=9,
        agent_name="ops",
        thread_id="t",
        session_id="s",
        capability_profile=RuntimeProfile(
            allowed_tool_names=["search_documents"],
            allowed_skill_names=["hr_policy", "secret"],
        ),
    )
    skills = manager.get_resolved_skills(runtime)
    assert list(skills.keys()) == ["hr_policy"]


@pytest.mark.asyncio
async def test_create_rejects_personal_skill(async_db_session, monkeypatch):
    tenant = Tenant(name="agent_skill", slug="agent_skill", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    owner = User(username="owner_sk", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(owner)
    await async_db_session.flush()
    await seed_default_policies(async_db_session, tenant.id)
    await async_db_session.commit()
    await async_db_session.refresh(owner)

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_catalog.services.TOOL_REGISTRY",
        {"search_documents": object()},
    )

    service = AgentCatalogService(tenant_id=tenant.id, db_session=async_db_session)
    with pytest.raises(ValidationError, match="Personal skill"):
        await service.create_agent(
            payload=AgentCreateRequest(
                name="Notes Bot",
                system_prompt="help",
                config=AgentCapabilityConfigDTO(skills=["my_notes"]),
            ),
            actor=ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="member"),
            assignable_skills=[
                AssignableSkill(name="my_notes", description="notes", scope=PERSONAL_SKILL_SCOPE),
            ],
        )


@pytest.mark.asyncio
async def test_agent_share_does_not_copy_collection_acl(async_db_session, monkeypatch):
    from apps.shared.authz.delegation import allows_delegated_read, has_agent_delegation

    tenant = Tenant(name="agent_acl", slug="agent_acl", config=None)
    async_db_session.add(tenant)
    await async_db_session.flush()
    owner = User(username="owner_acl", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    peer = User(username="peer_acl", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add_all([owner, peer])
    await async_db_session.flush()
    await seed_default_policies(async_db_session, tenant.id)
    collection = DocumentCollection(tenant_id=tenant.id, name="hr-kb", description=None, owner_id=owner.id)
    async_db_session.add(collection)
    await async_db_session.commit()
    await async_db_session.refresh(owner)
    await async_db_session.refresh(peer)
    await async_db_session.refresh(collection)

    monkeypatch.setattr(
        "apps.tenant_app_service.agent_catalog.services.TOOL_REGISTRY",
        {"search_documents": object()},
    )

    service = AgentCatalogService(tenant_id=tenant.id, db_session=async_db_session)
    created = await service.create_agent(
        payload=AgentCreateRequest(
            name="HR Bot",
            system_prompt="hr",
            config=AgentCapabilityConfigDTO(
                default_tools=["search_documents"],
                knowledge_base_ids=[collection.id],
            ),
        ),
        actor=ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="member"),
    )

    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type="agent",
            resource_id=created.id,
            principal_type="user",
            principal_id=str(peer.id),
            permission="read",
            effect="allow",
            created_by=owner.id,
        )
    )
    await async_db_session.flush()

    copied = (
        (
            await async_db_session.execute(
                select(AclGrant).where(
                    AclGrant.resource_type == RESOURCE_TYPE_DOCUMENT_COLLECTION,
                    AclGrant.resource_id == collection.id,
                    AclGrant.principal_id == str(peer.id),
                )
            )
        )
        .scalars()
        .all()
    )
    assert copied == []

    peer_can_read = await evaluate_resource_action(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=peer.id,
        user_role="member",
        resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
        resource_id=collection.id,
        resource_owner_id=owner.id,
        action=ABAC_ACTION_READ,
        has_manage_permission=False,
    )
    assert peer_can_read is False

    assert await has_agent_delegation(
        async_db_session,
        tenant_id=tenant.id,
        agent_id=created.id,
        user_id=peer.id,
        owner_id=owner.id,
    )
    attached_ids = [collection.id]
    assert await allows_delegated_read(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=peer.id,
        user_role="member",
        resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
        resource_id=collection.id,
        resource_owner_id=owner.id,
        action=ABAC_ACTION_READ,
        delegated_ids=attached_ids,
    )
    assert not await allows_delegated_read(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=peer.id,
        user_role="member",
        resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
        resource_id=collection.id,
        resource_owner_id=owner.id,
        action=ABAC_ACTION_READ,
        delegated_ids=None,
    )

    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=collection.id,
            principal_type="user",
            principal_id=str(peer.id),
            permission="read",
            effect="deny",
            created_by=owner.id,
        )
    )
    await async_db_session.flush()
    assert not await allows_delegated_read(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=peer.id,
        user_role="member",
        resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
        resource_id=collection.id,
        resource_owner_id=owner.id,
        action=ABAC_ACTION_READ,
        delegated_ids=attached_ids,
    )


def test_viewer_cannot_invoke_chat_without_chat_access():
    viewer = DEFAULT_ROLE_PERMISSIONS["viewer"]
    assert any(ta_permission_implies(granted, TenantAppPermissions.AGENTS_READ) for granted in viewer)
    assert not any(ta_permission_implies(granted, TenantAppPermissions.CHAT_ACCESS) for granted in viewer)
