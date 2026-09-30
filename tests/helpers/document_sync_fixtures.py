"""Shared fixtures for document source sync tests."""

from __future__ import annotations

from apps.shared.db.models import DocumentSourceProvider, Tenant, User
from apps.shared.document.source_provider_repository import DocumentSourceProviderRepository
from apps.shared.document.sync_types import DEFAULT_DOCUMENT_SOURCE_PROVIDER


async def create_tenant_and_user(
    session,
    *,
    tenant_name: str,
    username: str,
    role: str = "member",
) -> tuple[Tenant, User]:
    tenant = Tenant(name=tenant_name, slug=tenant_name.lower().replace(" ", "-"), status="active")
    session.add(tenant)
    await session.flush()
    user = User(
        username=username,
        email=f"{username}@test-sync.example",
        hashed_password="hashed",
        role=role,
        tenant_id=tenant.id,
        status="active",
    )
    session.add(user)
    await session.flush()
    await session.refresh(tenant)
    await session.refresh(user)
    return tenant, user


async def create_google_drive_provider(
    session,
    *,
    tenant_id: int,
    enabled: bool = True,
    client_id: str = "test-client-id",
    client_secret: str = "test-client-secret",
) -> DocumentSourceProvider:
    repo = DocumentSourceProviderRepository(session)
    return await repo.upsert_provider(
        tenant_id=tenant_id,
        provider=DEFAULT_DOCUMENT_SOURCE_PROVIDER,
        enabled=enabled,
        config={"client_id": client_id, "client_secret": client_secret},
    )
