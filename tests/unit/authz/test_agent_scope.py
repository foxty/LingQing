"""Unit tests for agent attachment scope clipping (user ACL ∩ agent IDs)."""

from uuid import uuid4

import pytest
from sqlalchemy import column

from apps.shared.authz.agent_scope import combine_agent_scope
from apps.shared.authz.authz_query_builder import AuthzSqlFilter
from apps.shared.core.policy_seed import seed_default_policies
from apps.shared.db.models import User
from apps.shared.document.collection_service import DocumentAccessScope, DocumentCollectionService
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ
from apps.shared.search.search_service import SearchService
from tests.helpers.document_fixtures import create_document_collection, create_tenant_user


def test_combine_agent_scope_passthrough_without_allowlist():
    user_scope = AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)
    combined = combine_agent_scope(
        user_scope=user_scope,
        id_column=column("id"),
        allowed_ids=None,
    )
    assert combined.allow_all is True
    assert combined.deny_all is False


def test_combine_agent_scope_empty_allowlist_denies():
    user_scope = AuthzSqlFilter(allow_all=True, deny_all=False, clause=None)
    combined = combine_agent_scope(
        user_scope=user_scope,
        id_column=column("id"),
        allowed_ids=[],
    )
    assert combined.deny_all is True


def test_combine_agent_scope_intersects_user_deny():
    user_scope = AuthzSqlFilter(allow_all=False, deny_all=True, clause=None)
    combined = combine_agent_scope(
        user_scope=user_scope,
        id_column=column("id"),
        allowed_ids=[1, 2],
    )
    assert combined.deny_all is True


def test_combine_agent_scope_intersects_user_clause():
    user_scope = AuthzSqlFilter(allow_all=False, deny_all=False, clause=column("owner_id") == 9)
    combined = combine_agent_scope(
        user_scope=user_scope,
        id_column=column("id"),
        allowed_ids=[1, 2],
    )
    assert combined.deny_all is False
    assert combined.allow_all is False
    assert combined.clause is not None


def test_search_keeps_user_deny_with_agent_clip():
    service = SearchService.__new__(SearchService)
    denied = DocumentAccessScope(
        deny_all=True,
        allow_all=False,
        document_filter=None,
        index_parent_filter=None,
    )
    clipped = service._clip_collection_scope(denied, [11, 12])
    assert clipped.deny_all is True
    assert clipped.document_filter is None


def _suffix() -> str:
    return uuid4().hex[:8]


@pytest.mark.asyncio
async def test_shared_user_cannot_read_collection_without_acl(async_db_session):
    tenant, owner = await create_tenant_user(
        async_db_session, tenant_name=f"scope-{_suffix()}", username=f"owner-{_suffix()}"
    )
    peer = User(
        username=f"peer-{_suffix()}",
        email=None,
        hashed_password="hashed",
        role="member",
        tenant_id=tenant.id,
    )
    async_db_session.add(peer)
    await async_db_session.flush()
    await seed_default_policies(async_db_session, tenant.id)
    collection = await create_document_collection(
        async_db_session, tenant_id=tenant.id, owner_id=owner.id, name="kb"
    )
    await async_db_session.commit()
    await async_db_session.refresh(peer)

    service = DocumentCollectionService(tenant.id, async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=peer.id, user_role="member")
    with pytest.raises(Exception):
        await service.require_collection_access(
            collection_id=collection.id,
            actor=actor,
            action=ABAC_ACTION_READ,
        )
