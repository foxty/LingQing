"""Unit tests for collection-level can_write / can_manage capabilities."""

from __future__ import annotations

import pytest

from apps.shared.db.models import AbacPolicy, AclGrant, ResourceAcl, User
from apps.shared.document.collection_service import DocumentCollectionService
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_DOCUMENT_COLLECTION
from tests.helpers.document_fixtures import create_document_collection, create_tenant_user


async def _add_tenant_user(session, *, tenant_id: int, username: str, role: str = "viewer") -> User:
    user = User(
        username=username,
        email=None,
        hashed_password="hashed",
        role=role,
        tenant_id=tenant_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _seed_owner_only_collection_abac(session, *, tenant_id: int, created_by: int) -> None:
    for index, action in enumerate(("read", "write"), start=1):
        session.add(
            AbacPolicy(
                id=index,
                tenant_id=tenant_id,
                name=f"collection_owner_{action}",
                description=None,
                resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
                action=action,
                expression=":user.id equals :resource.owner_id",
                status="active",
                created_by=created_by,
                updated_by=created_by,
            )
        )
    await session.commit()


async def _grant_collection_acl(
    session,
    *,
    tenant_id: int,
    collection_id: int,
    owner_id: int,
    grantee_user_id: int,
    permission: str,
    created_by: int,
) -> None:
    session.add(
        ResourceAcl(
            tenant_id=tenant_id,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=collection_id,
            owner_id=owner_id,
            status="active",
        )
    )
    session.add(
        AclGrant(
            tenant_id=tenant_id,
            resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
            resource_id=collection_id,
            principal_type="user",
            principal_id=str(grantee_user_id),
            permission=permission,
            effect="allow",
            created_by=created_by,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_collection_capabilities_owner_can_write_and_manage(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="cap_owner", username="owner_user")
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=owner.id)
    service = DocumentCollectionService(tenant_id=tenant.id, db_session=async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role=owner.role)

    response = await service.get_collection_for_actor(collection_id=collection.id, actor=actor)

    assert response.can_write is True
    assert response.can_manage is True


@pytest.mark.asyncio
async def test_collection_capabilities_acl_read_grants_read_only(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="cap_read", username="owner_read")
    sharee = await _add_tenant_user(async_db_session, tenant_id=tenant.id, username="sharee_read", role="viewer")
    await _seed_owner_only_collection_abac(async_db_session, tenant_id=tenant.id, created_by=owner.id)
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=owner.id)
    await _grant_collection_acl(
        async_db_session,
        tenant_id=tenant.id,
        collection_id=collection.id,
        owner_id=owner.id,
        grantee_user_id=sharee.id,
        permission="read",
        created_by=owner.id,
    )

    service = DocumentCollectionService(tenant_id=tenant.id, db_session=async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=sharee.id, user_role=sharee.role)

    response = await service.get_collection_for_actor(collection_id=collection.id, actor=actor)

    assert response.can_write is False
    assert response.can_manage is False


@pytest.mark.asyncio
async def test_collection_capabilities_acl_write_grants_write(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="cap_write", username="owner_write")
    editor = await _add_tenant_user(async_db_session, tenant_id=tenant.id, username="editor_write", role="member")
    await _seed_owner_only_collection_abac(async_db_session, tenant_id=tenant.id, created_by=owner.id)
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=owner.id)
    await _grant_collection_acl(
        async_db_session,
        tenant_id=tenant.id,
        collection_id=collection.id,
        owner_id=owner.id,
        grantee_user_id=editor.id,
        permission="write",
        created_by=owner.id,
    )

    service = DocumentCollectionService(tenant_id=tenant.id, db_session=async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=editor.id, user_role=editor.role)

    response = await service.get_collection_for_actor(collection_id=collection.id, actor=actor)

    assert response.can_write is True
    assert response.can_manage is False
