"""Unit tests for agent-scoped delegation."""

from uuid import uuid4

import pytest
from sqlalchemy import column

from apps.shared.authz.authz_query_builder import AuthzSqlFilter
from apps.shared.authz.delegation import (
    allows_delegated_read,
    combine_agent_scope,
    filter_explicit_deny_ids,
    has_agent_delegation,
)
from apps.shared.core.exceptions import AuthorizationError
from apps.shared.core.policy_seed import seed_default_policies
from apps.shared.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.data_source.service import DataSourceService
from apps.shared.db.models import AclGrant, User
from apps.shared.document.collection_service import DocumentAccessScope, DocumentCollectionService
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    ABAC_ACTION_WRITE,
    ACL_EFFECT_ALLOW,
    ACL_EFFECT_DENY,
    ACL_PERMISSION_READ,
    ACL_PRINCIPAL_USER,
    RESOURCE_TYPE_AGENT,
    RESOURCE_TYPE_DOCUMENT_COLLECTION,
)
from apps.shared.search.search_service import SearchService
from apps.tenant_app_service.agents.domain import AgentCapabilityProfile
from tests.helpers.data_source_fixtures import create_data_source
from tests.helpers.document_fixtures import create_document_collection, create_tenant_user


def test_combine_agent_scope_passthrough_without_allowlist():
    user_scope = AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)
    combined = combine_agent_scope(
        user_scope=user_scope,
        id_column=column("id"),
        allowed_ids=None,
        delegate=False,
    )
    assert combined.allow_all is True
    assert combined.deny_all is False


def test_combine_agent_scope_empty_allowlist_denies():
    user_scope = AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)
    combined = combine_agent_scope(
        user_scope=user_scope,
        id_column=column("id"),
        allowed_ids=[],
        delegate=True,
    )
    assert combined.deny_all is True


def test_combine_agent_scope_delegate_uses_allowlist_only():
    user_scope = AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)
    combined = combine_agent_scope(
        user_scope=user_scope,
        id_column=column("id"),
        allowed_ids=[1, 2],
        delegate=True,
    )
    assert combined.deny_all is False
    assert combined.allow_all is False
    assert combined.clause is not None


def test_combine_agent_scope_without_delegate_keeps_user_deny():
    user_scope = AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)
    combined = combine_agent_scope(
        user_scope=user_scope,
        id_column=column("id"),
        allowed_ids=[1, 2],
        delegate=False,
    )
    assert combined.deny_all is True


def test_combine_agent_scope_without_delegate_intersects_user_clause():
    user_scope = AuthzSqlFilter(allow_all=False, deny_all=False, clause=column("owner_id") == 9)
    combined = combine_agent_scope(
        user_scope=user_scope,
        id_column=column("id"),
        allowed_ids=[1, 2],
        delegate=False,
    )
    assert combined.deny_all is False
    assert combined.allow_all is False
    assert combined.clause is not None


def test_capability_profile_delegated_ids_only_when_delegate():
    attached = AgentCapabilityProfile(allowed_data_source_ids=[7], delegate=False)
    assert attached.delegated(attached.allowed_data_source_ids) is None

    shared = AgentCapabilityProfile(allowed_data_source_ids=[7, 8], delegate=True)
    assert shared.delegated(shared.allowed_data_source_ids) == [7, 8]
    assert shared.delegated([]) is None


def test_search_clips_attached_collections_for_delegate_even_if_user_denied():
    service = SearchService.__new__(SearchService)
    service.delegate = True
    denied = DocumentAccessScope(
        deny_all=True,
        allow_all=False,
        document_filter=None,
        index_parent_filter=None,
    )
    clipped = service._clip_collection_scope(denied, [11, 12])
    assert clipped.deny_all is False
    assert clipped.document_filter is not None


def test_search_keeps_user_deny_when_not_delegated():
    service = SearchService.__new__(SearchService)
    service.delegate = False
    denied = DocumentAccessScope(
        deny_all=True,
        allow_all=False,
        document_filter=None,
        index_parent_filter=None,
    )
    clipped = service._clip_collection_scope(denied, [11, 12])
    assert clipped.deny_all is True
    assert clipped.document_filter is None


def test_search_delegated_ids_helper_requires_delegate_flag():
    service = SearchService.__new__(SearchService)
    service.delegate = False
    assert service._delegated_ids([3]) is None
    service.delegate = True
    assert service._delegated_ids([3]) == [3]
    assert service._delegated_ids([]) is None


def _suffix() -> str:
    return uuid4().hex[:8]


async def _peer_actor(session, tenant_id: int, username: str) -> tuple[User, ActorContext]:
    peer = User(
        username=username,
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant_id,
    )
    session.add(peer)
    await session.commit()
    await session.refresh(peer)
    return peer, ActorContext(tenant_id=tenant_id, user_id=peer.id, user_role="member")


@pytest.mark.asyncio
async def test_has_agent_delegation_owner_share_and_stranger(async_db_session):
    tenant, owner = await create_tenant_user(
        async_db_session, tenant_name=f"delg-own-{_suffix()}", username=f"owner-{_suffix()}"
    )
    peer, _ = await _peer_actor(async_db_session, tenant.id, f"peer-{_suffix()}")
    stranger, _ = await _peer_actor(async_db_session, tenant.id, f"stranger-{_suffix()}")
    agent_id = 9_001

    assert await has_agent_delegation(
        async_db_session,
        tenant_id=tenant.id,
        agent_id=agent_id,
        user_id=owner.id,
        owner_id=owner.id,
    )
    assert not await has_agent_delegation(
        async_db_session,
        tenant_id=tenant.id,
        agent_id=agent_id,
        user_id=peer.id,
        owner_id=owner.id,
    )
    assert not await has_agent_delegation(
        async_db_session,
        tenant_id=tenant.id,
        agent_id=agent_id,
        user_id=stranger.id,
        owner_id=owner.id,
    )

    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type=RESOURCE_TYPE_AGENT,
            resource_id=agent_id,
            principal_type=ACL_PRINCIPAL_USER,
            principal_id=str(peer.id),
            permission=ACL_PERMISSION_READ,
            effect=ACL_EFFECT_ALLOW,
            created_by=owner.id,
        )
    )
    await async_db_session.flush()

    assert await has_agent_delegation(
        async_db_session,
        tenant_id=tenant.id,
        agent_id=agent_id,
        user_id=peer.id,
        owner_id=owner.id,
    )
    assert not await has_agent_delegation(
        async_db_session,
        tenant_id=tenant.id,
        agent_id=agent_id,
        user_id=stranger.id,
        owner_id=owner.id,
    )


@pytest.mark.asyncio
async def test_filter_explicit_deny_ids_drops_denied_keeps_rest(async_db_session):
    tenant, owner = await create_tenant_user(
        async_db_session, tenant_name=f"delg-deny-{_suffix()}", username=f"owner-{_suffix()}"
    )
    peer, _ = await _peer_actor(async_db_session, tenant.id, f"peer-{_suffix()}")
    kept = 21
    blocked = 22
    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=blocked,
            principal_type=ACL_PRINCIPAL_USER,
            principal_id=str(peer.id),
            permission=ACL_PERMISSION_READ,
            effect=ACL_EFFECT_DENY,
            created_by=owner.id,
        )
    )
    await async_db_session.flush()

    usable = await filter_explicit_deny_ids(
        async_db_session,
        tenant_id=tenant.id,
        user_id=peer.id,
        user_role="member",
        resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
        resource_ids=[kept, blocked],
    )
    assert usable == [kept]


@pytest.mark.asyncio
async def test_collection_read_delegated_vs_catalog(async_db_session):
    tenant, owner = await create_tenant_user(
        async_db_session, tenant_name=f"delg-kb-{_suffix()}", username=f"owner-{_suffix()}"
    )
    await seed_default_policies(async_db_session, tenant.id)
    peer, peer_actor = await _peer_actor(async_db_session, tenant.id, f"peer-{_suffix()}")
    collection = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        name="hr-kb",
    )
    other = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        name="other-kb",
    )
    service = DocumentCollectionService(tenant.id, async_db_session)

    with pytest.raises(AuthorizationError):
        await service.require_collection_access(
            collection_id=collection.id,
            actor=peer_actor,
            action=ABAC_ACTION_READ,
        )
    with pytest.raises(AuthorizationError):
        await service.require_collection_access(
            collection_id=collection.id,
            actor=peer_actor,
            action=ABAC_ACTION_READ,
            delegated_ids=None,
        )

    allowed = await service.require_collection_access(
        collection_id=collection.id,
        actor=peer_actor,
        action=ABAC_ACTION_READ,
        delegated_ids=[collection.id],
    )
    assert allowed.id == collection.id

    with pytest.raises(AuthorizationError):
        await service.require_collection_access(
            collection_id=other.id,
            actor=peer_actor,
            action=ABAC_ACTION_READ,
            delegated_ids=[collection.id],
        )
    with pytest.raises(AuthorizationError):
        await service.require_collection_access(
            collection_id=collection.id,
            actor=peer_actor,
            action=ABAC_ACTION_WRITE,
            delegated_ids=[collection.id],
        )

    async_db_session.add(
        AclGrant(
            tenant_id=tenant.id,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=collection.id,
            principal_type=ACL_PRINCIPAL_USER,
            principal_id=str(peer.id),
            permission=ACL_PERMISSION_READ,
            effect=ACL_EFFECT_DENY,
            created_by=owner.id,
        )
    )
    await async_db_session.flush()
    with pytest.raises(AuthorizationError):
        await service.require_collection_access(
            collection_id=collection.id,
            actor=peer_actor,
            action=ABAC_ACTION_READ,
            delegated_ids=[collection.id],
        )


@pytest.mark.asyncio
async def test_data_source_read_delegated_vs_catalog(async_db_session):
    tenant, owner = await create_tenant_user(
        async_db_session, tenant_name=f"delg-ds-{_suffix()}", username=f"owner-{_suffix()}"
    )
    await seed_default_policies(async_db_session, tenant.id)
    _, peer_actor = await _peer_actor(async_db_session, tenant.id, f"peer-{_suffix()}")
    data_source = await create_data_source(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        name=f"sales-{_suffix()}",
    )
    other = await create_data_source(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        name=f"other-{_suffix()}",
    )
    service = DataSourceService(
        tenant_id=tenant.id,
        data_source_repo=DataSourceRepository(async_db_session),
        asset_repo=AssetMetadataRepository(async_db_session),
    )

    with pytest.raises(AuthorizationError):
        await service.require_read_access_for_actor(
            data_source_id=data_source.id,
            actor=peer_actor,
        )

    readable = await service.require_read_access_for_actor(
        data_source_id=data_source.id,
        actor=peer_actor,
        delegated_ids=[data_source.id],
    )
    assert readable.id == data_source.id

    with pytest.raises(AuthorizationError):
        await service.require_read_access_for_actor(
            data_source_id=other.id,
            actor=peer_actor,
            delegated_ids=[data_source.id],
        )
    with pytest.raises(AuthorizationError):
        await service.require_data_source_access_for_actor(
            data_source_id=data_source.id,
            actor=peer_actor,
            action=ABAC_ACTION_WRITE,
            delegated_ids=[data_source.id],
        )


@pytest.mark.asyncio
async def test_allows_delegated_read_ignores_ids_outside_allowlist(async_db_session):
    tenant, owner = await create_tenant_user(
        async_db_session, tenant_name=f"delg-miss-{_suffix()}", username=f"owner-{_suffix()}"
    )
    await seed_default_policies(async_db_session, tenant.id)
    peer, _ = await _peer_actor(async_db_session, tenant.id, f"peer-{_suffix()}")
    collection = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        name="private-kb",
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
        delegated_ids=[collection.id + 99],
    )
    assert not await allows_delegated_read(
        db_session=async_db_session,
        tenant_id=tenant.id,
        user_id=peer.id,
        user_role="member",
        resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
        resource_id=collection.id,
        resource_owner_id=owner.id,
        action=ABAC_ACTION_WRITE,
        delegated_ids=[collection.id],
    )
