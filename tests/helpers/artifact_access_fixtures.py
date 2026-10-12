"""Synthetic fixtures for artifact list/inject ACL tests."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AclGrant, Artifact, ResourceAcl, Tenant, User


async def create_tenant_with_users(
    session: AsyncSession,
    *,
    owner_username: str,
    peer_username: str,
    owner_role: str = "member",
    peer_role: str = "member",
) -> tuple[Tenant, User, User]:
    tenant = Tenant(name=f"tenant_{owner_username}", slug=f"tenant_{owner_username}", config=None)
    session.add(tenant)
    await session.flush()

    owner = User(
        username=owner_username,
        email=None,
        hashed_password="hashed",
        role=owner_role,
        tenant_id=tenant.id,
    )
    peer = User(
        username=peer_username,
        email=None,
        hashed_password="hashed",
        role=peer_role,
        tenant_id=tenant.id,
    )
    session.add_all([owner, peer])
    await session.flush()
    await session.commit()
    await session.refresh(tenant)
    await session.refresh(owner)
    await session.refresh(peer)
    return tenant, owner, peer


async def create_standalone_artifact(
    session: AsyncSession,
    *,
    tenant_id: int,
    owner_id: int,
    resource_id: int,
    artifact_type: str = "report",
    title: str = "Synthetic Report",
) -> Artifact:
    artifact = Artifact(
        tenant_id=tenant_id,
        artifact_type=artifact_type,
        resource_id=resource_id,
        owner_id=owner_id,
        title=title,
        url=f"/{artifact_type}s/{resource_id}/embed",
        artifact_metadata={"synthetic": True},
        source_thread_id=None,
    )
    session.add(artifact)
    await session.flush()
    await session.commit()
    await session.refresh(artifact)
    return artifact


async def grant_artifact_acl(
    session: AsyncSession,
    *,
    tenant_id: int,
    artifact_type: str,
    resource_id: int,
    owner_id: int,
    grantee_user_id: int,
    permission: str,
    effect: str = "allow",
    created_by: int | None = None,
) -> None:
    session.add(
        ResourceAcl(
            tenant_id=tenant_id,
            resource_type=artifact_type,
            resource_id=resource_id,
            owner_id=owner_id,
            status="active",
        )
    )
    session.add(
        AclGrant(
            tenant_id=tenant_id,
            resource_type=artifact_type,
            resource_id=resource_id,
            principal_type="user",
            principal_id=str(grantee_user_id),
            permission=permission,
            effect=effect,
            created_by=created_by or owner_id,
        )
    )
    await session.commit()
