"""Unit tests for document collection authz and dedup behavior."""

import pytest

from apps.shared.core.exceptions import DuplicateResourceError, ValidationError
from apps.shared.document.repository import DBDocumentRepository
from apps.shared.document.collection_service import DocumentCollectionService
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ, ABAC_ACTION_WRITE, RESOURCE_TYPE_DOCUMENT_COLLECTION
from tests.helpers.document_fixtures import create_document, create_document_collection, create_tenant_user


async def seed_collection_owner_policies(session, tenant_id: int, *, base_id: int = 9000) -> None:
    from apps.shared.db.models import AbacPolicy

    for offset, action in enumerate((ABAC_ACTION_READ, ABAC_ACTION_WRITE)):
        session.add(
            AbacPolicy(
                id=base_id + offset,
                tenant_id=tenant_id,
                name=f"collection-owner-{action}",
                description=None,
                resource_type=RESOURCE_TYPE_DOCUMENT_COLLECTION,
                action=action,
                expression=':user.role equals "admin" or :user.id equals :resource.owner_id',
                status="active",
            )
        )
    await session.commit()


@pytest.mark.asyncio
async def test_build_document_access_scope_owner_can_read_own_collection(async_db_session):
    tenant, user = await create_tenant_user(async_db_session, tenant_name="t1", username="u1")
    await seed_collection_owner_policies(async_db_session, tenant.id)
    collection = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        name="Engineering",
    )
    await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=collection.id,
        filename="a.pdf",
        file_hash="hash-a",
    )

    service = DocumentCollectionService(tenant.id, async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=user.id, user_role="member")
    scope = await service.build_document_access_scope(actor=actor, action=ABAC_ACTION_READ)

    assert scope.deny_all is False
    assert scope.allow_all is False
    assert scope.document_filter is not None

    repo = DBDocumentRepository(async_db_session)
    docs = await repo.list_by_tenant(tenant.id, abac_filter=scope.document_filter)
    assert len(docs) == 1
    assert docs[0].filename == "a.pdf"


@pytest.mark.asyncio
async def test_build_document_access_scope_index_parent_filter(async_db_session):
    from sqlalchemy import select

    from apps.shared.db.models import ResourceIndex
    from apps.shared.domain.types import RESOURCE_TYPE_DOCUMENT

    tenant, owner = await create_tenant_user(async_db_session, tenant_name="t1b", username="u1b")
    await seed_collection_owner_policies(async_db_session, tenant.id, base_id=9100)
    from apps.shared.db.models import User

    other = User(username="other2", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    allowed = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        name="Allowed",
    )
    denied = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=other.id,
        name="Denied",
    )
    allowed_doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        collection_id=allowed.id,
        filename="allowed.pdf",
        file_hash="hash-allowed",
    )
    denied_doc = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=other.id,
        collection_id=denied.id,
        filename="denied.pdf",
        file_hash="hash-denied",
    )

    for doc in (allowed_doc, denied_doc):
        async_db_session.add(
            ResourceIndex(
                tenant_id=tenant.id,
                resource_type=RESOURCE_TYPE_DOCUMENT,
                resource_id=doc.id,
                owner_id=doc.owner_id,
                parent_id=doc.collection_id,
                tokenized_content=doc.filename,
            )
        )
    await async_db_session.commit()

    service = DocumentCollectionService(tenant.id, async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="member")
    scope = await service.build_document_access_scope(actor=actor, action=ABAC_ACTION_READ)

    assert scope.index_parent_filter is not None
    stmt = (
        select(ResourceIndex.resource_id)
        .where(
            ResourceIndex.tenant_id == tenant.id,
            ResourceIndex.resource_type == RESOURCE_TYPE_DOCUMENT,
            scope.index_parent_filter,
        )
    )
    result = await async_db_session.execute(stmt)
    visible_ids = set(result.scalars().all())
    assert visible_ids == {allowed_doc.id}


@pytest.mark.asyncio
async def test_build_document_access_scope_other_user_denied_by_default(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="t2", username="owner")
    await seed_collection_owner_policies(async_db_session, tenant.id)
    from apps.shared.db.models import User

    other = User(username="other", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    collection = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        name="HR",
    )
    await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        collection_id=collection.id,
    )

    service = DocumentCollectionService(tenant.id, async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=other.id, user_role="member")
    scope = await service.build_document_access_scope(actor=actor, action=ABAC_ACTION_READ)

    repo = DBDocumentRepository(async_db_session)
    docs = await repo.list_by_tenant(tenant.id, abac_filter=scope.document_filter)
    assert docs == []


@pytest.mark.asyncio
async def test_dedup_is_scoped_to_collection(async_db_session):
    tenant, user = await create_tenant_user(async_db_session, tenant_name="t3", username="dedup-user")
    coll_a = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id, name="A")
    coll_b = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id, name="B")

    await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=user.id,
        collection_id=coll_a.id,
        file_hash="same-hash",
        filename="shared.pdf",
    )

    repo = DBDocumentRepository(async_db_session)
    assert await repo.find_by_hash(tenant.id, "same-hash", coll_a.id) is not None
    assert await repo.find_by_hash(tenant.id, "same-hash", coll_b.id) is None


@pytest.mark.asyncio
async def test_require_collection_write_for_delete(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="t4", username="owner2")
    await seed_collection_owner_policies(async_db_session, tenant.id)
    from apps.shared.core.exceptions import AuthorizationError
    from apps.shared.db.models import User

    other = User(username="viewer", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    collection = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        name="Private",
    )

    service = DocumentCollectionService(tenant.id, async_db_session)
    with pytest.raises(AuthorizationError):
        await service.require_collection_access(
            collection_id=collection.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=other.id, user_role="member"),
            action=ABAC_ACTION_WRITE,
        )


@pytest.mark.asyncio
async def test_require_document_access_inherits_collection_read(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="t6", username="doc-owner")
    await seed_collection_owner_policies(async_db_session, tenant.id, base_id=9200)
    collection = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        name="Readable",
    )
    document = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        collection_id=collection.id,
        filename="readable.pdf",
        file_hash="hash-readable",
    )

    service = DocumentCollectionService(tenant.id, async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=owner.id, user_role="member")
    collection_id = await service.require_document_access(
        document_id=document.id,
        actor=actor,
        action=ABAC_ACTION_READ,
    )
    assert collection_id == collection.id


@pytest.mark.asyncio
async def test_require_document_access_denied_when_collection_inaccessible(async_db_session):
    tenant, owner = await create_tenant_user(async_db_session, tenant_name="t7", username="doc-owner2")
    await seed_collection_owner_policies(async_db_session, tenant.id, base_id=9300)
    from apps.shared.core.exceptions import AuthorizationError
    from apps.shared.db.models import User

    other = User(username="stranger", email=None, hashed_password="hashed", role="member", tenant_id=tenant.id)
    async_db_session.add(other)
    await async_db_session.commit()
    await async_db_session.refresh(other)

    collection = await create_document_collection(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        name="Private Docs",
    )
    document = await create_document(
        async_db_session,
        tenant_id=tenant.id,
        owner_id=owner.id,
        collection_id=collection.id,
        filename="private.pdf",
        file_hash="hash-private",
    )

    service = DocumentCollectionService(tenant.id, async_db_session)
    with pytest.raises(AuthorizationError):
        await service.require_document_access(
            document_id=document.id,
            actor=ActorContext(tenant_id=tenant.id, user_id=other.id, user_role="member"),
            action=ABAC_ACTION_READ,
        )


@pytest.mark.asyncio
async def test_delete_non_empty_collection_rejected(async_db_session):
    tenant, user = await create_tenant_user(async_db_session, tenant_name="t5", username="owner3")
    collection = await create_document_collection(async_db_session, tenant_id=tenant.id, owner_id=user.id)
    await create_document(async_db_session, tenant_id=tenant.id, owner_id=user.id, collection_id=collection.id)

    service = DocumentCollectionService(tenant.id, async_db_session)
    actor = ActorContext(tenant_id=tenant.id, user_id=user.id, user_role="admin")
    with pytest.raises(ValidationError):
        await service.delete_collection(collection_id=collection.id, actor=actor)
