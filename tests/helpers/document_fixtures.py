"""Test helpers for document collection fixtures."""

from apps.shared.db.models import Document, DocumentCollection, Tenant, User


async def create_tenant_user(session, *, tenant_name: str, username: str, role: str = "member"):
    tenant = Tenant(name=tenant_name, slug=tenant_name, config=None)
    session.add(tenant)
    await session.commit()
    await session.refresh(tenant)

    user = User(
        username=username,
        email=None,
        hashed_password="hashed",
        role=role,
        tenant_id=tenant.id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return tenant, user


async def create_document_collection(
    session,
    *,
    tenant_id: int,
    owner_id: int,
    name: str = "General",
    description: str | None = None,
) -> DocumentCollection:
    collection = DocumentCollection(
        tenant_id=tenant_id,
        name=name,
        owner_id=owner_id,
        description=description,
    )
    session.add(collection)
    await session.commit()
    await session.refresh(collection)
    return collection


async def create_document(
    session,
    *,
    tenant_id: int,
    owner_id: int,
    collection_id: int | None = None,
    filename: str = "test.pdf",
    file_url: str = "file://test",
    file_hash: str = "hash",
) -> Document:
    if collection_id is None:
        collection = await create_document_collection(
            session,
            tenant_id=tenant_id,
            owner_id=owner_id,
        )
        collection_id = collection.id

    document = Document(
        tenant_id=tenant_id,
        collection_id=collection_id,
        owner_id=owner_id,
        filename=filename,
        file_url=file_url,
        file_size=10,
        file_hash=file_hash,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return document
