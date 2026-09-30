"""Helpers for document source sync integration tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import jwt

from apps.shared.db.models import AbacPolicy, AclGrant, ResourceAcl, Tenant, TenantMembership, User
from apps.shared.domain.types import RESOURCE_TYPE_DOCUMENT_COLLECTION
from apps.shared.db.session import get_db
from apps.tenant_app_service.server import app
from tests.integration.conftest import TEST_SECRET_KEY, make_auth_headers


def create_user_token(*, user_id: int, username: str, role: str, tenant_id: int, tenant_name: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    payload = {
        "user_id": user_id,
        "sub": username,
        "role": role,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "exp": expire,
    }
    return jwt.encode(payload, TEST_SECRET_KEY, algorithm="HS256")


async def seed_document_sync_tenant(session) -> dict:
    """Create tenant with admin and member users."""
    suffix = uuid4().hex[:8]
    tenant = Tenant(
        name=f"doc_sync_{suffix}",
        slug=f"doc_sync_{suffix}",
        status="active",
    )
    session.add(tenant)
    await session.flush()

    admin = User(
        username=f"admin_{suffix}",
        email=f"admin_{suffix}@test-sync.example",
        hashed_password="$2b$12$dummy",
        tenant_id=tenant.id,
        role="admin",
        status="active",
    )
    member = User(
        username=f"member_{suffix}",
        email=f"member_{suffix}@test-sync.example",
        hashed_password="$2b$12$dummy",
        tenant_id=tenant.id,
        role="member",
        status="active",
    )
    viewer = User(
        username=f"viewer_{suffix}",
        email=f"viewer_{suffix}@test-sync.example",
        hashed_password="$2b$12$dummy",
        tenant_id=tenant.id,
        role="viewer",
        status="active",
    )
    session.add_all([admin, member, viewer])
    await session.flush()

    session.add_all(
        [
            TenantMembership(tenant_id=tenant.id, user_id=admin.id, status="active"),
            TenantMembership(tenant_id=tenant.id, user_id=member.id, status="active"),
            TenantMembership(tenant_id=tenant.id, user_id=viewer.id, status="active"),
        ]
    )
    await session.flush()

    return {
        "tenant": tenant,
        "admin": admin,
        "member": member,
        "viewer": viewer,
        "admin_token": create_user_token(
            user_id=admin.id,
            username=admin.username,
            role=admin.role,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
        ),
        "member_token": create_user_token(
            user_id=member.id,
            username=member.username,
            role=member.role,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
        ),
        "viewer_token": create_user_token(
            user_id=viewer.id,
            username=viewer.username,
            role=viewer.role,
            tenant_id=tenant.id,
            tenant_name=tenant.name,
        ),
    }


async def seed_owner_only_collection_abac(session, *, tenant_id: int, created_by: int) -> None:
    """Restrict collection read/write to owners so ACL grants can delegate access."""
    for action in ("read", "write"):
        session.add(
            AbacPolicy(
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
    await session.flush()


async def grant_collection_acl(
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
    await session.flush()


async def configure_google_drive_source(client, token: str, *, enabled: bool = True) -> None:
    resp = await client.put(
        "/document-sources/google-drive",
        json={
            "client_id": "integration-client-id",
            "client_secret": "integration-client-secret",
            "enabled": enabled,
        },
        headers=make_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text


async def wire_test_client(session_factory):
    """Override FastAPI DB dependency to use the integration test session factory."""

    async def override_get_db():
        async with session_factory() as db_session:
            try:
                yield db_session
                await db_session.commit()
            except Exception:
                await db_session.rollback()
                raise
            finally:
                await db_session.close()

    app.dependency_overrides[get_db] = override_get_db


def clear_test_client_overrides() -> None:
    app.dependency_overrides.clear()
