"""Default ABAC policy seed definitions and helpers."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.repository import AbacPolicyRepository
from apps.shared.db.models import AbacPolicy
from apps.shared.domain.types import (
    ABAC_ACTION_READ,
    ABAC_ACTION_WRITE,
    RESOURCE_TYPE_AGENT,
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_DATA_SOURCE,
    RESOURCE_TYPE_DOCUMENT_COLLECTION,
)

DEFAULT_ABAC_POLICIES = [
    {
        "name": "Admin or Owner Read Access - Document Collections",
        "description": "Tenant admins can read all document collections; non-admin users can read their own collections",
        "resource_type": RESOURCE_TYPE_DOCUMENT_COLLECTION,
        "action": ABAC_ACTION_READ,
        "expression": ':user.role equals "admin" or :user.id equals :resource.owner_id',
    },
    {
        "name": "Admin or Owner Write Access - Document Collections",
        "description": "Tenant admins can write all document collections; non-admin users can write their own collections",
        "resource_type": RESOURCE_TYPE_DOCUMENT_COLLECTION,
        "action": ABAC_ACTION_WRITE,
        "expression": ':user.role equals "admin" or :user.id equals :resource.owner_id',
    },
    {
        "name": "Admin or Owner Read Access - API Connectors",
        "description": "Tenant admins can read all API connectors; non-admin users can read their own API connectors",
        "resource_type": RESOURCE_TYPE_API_CONNECTOR,
        "action": ABAC_ACTION_READ,
        "expression": ':user.role equals "admin" or :user.id equals :resource.owner_id',
    },
    {
        "name": "Admin or Owner Write Access - API Connectors",
        "description": "Tenant admins can write all API connectors; non-admin users can write their own API connectors",
        "resource_type": RESOURCE_TYPE_API_CONNECTOR,
        "action": ABAC_ACTION_WRITE,
        "expression": ':user.role equals "admin" or :user.id equals :resource.owner_id',
    },
    {
        "name": "Admin or Owner Read Access - Data Sources",
        "description": "Tenant admins can read all data sources; non-admin users can read their own data sources",
        "resource_type": RESOURCE_TYPE_DATA_SOURCE,
        "action": ABAC_ACTION_READ,
        "expression": ':user.role equals "admin" or :user.id equals :resource.owner_id',
    },
    {
        "name": "Admin or Owner Write Access - Data Sources",
        "description": "Tenant admins can write all data sources; non-admin users can write their own data sources",
        "resource_type": RESOURCE_TYPE_DATA_SOURCE,
        "action": ABAC_ACTION_WRITE,
        "expression": ':user.role equals "admin" or :user.id equals :resource.owner_id',
    },
    {
        "name": "Admin or Owner Read Access - Agents",
        "description": "Tenant admins can read all custom agents; non-admin users can read their own agents",
        "resource_type": RESOURCE_TYPE_AGENT,
        "action": ABAC_ACTION_READ,
        "expression": ':user.role equals "admin" or :user.id equals :resource.owner_id',
    },
    {
        "name": "Admin or Owner Write Access - Agents",
        "description": "Tenant admins can write all custom agents; non-admin users can write their own agents",
        "resource_type": RESOURCE_TYPE_AGENT,
        "action": ABAC_ACTION_WRITE,
        "expression": ':user.role equals "admin" or :user.id equals :resource.owner_id',
    },
]


async def seed_default_policies(db: AsyncSession, tenant_id: int) -> dict:
    """Seed default ABAC policies for a tenant. Idempotent.

    Returns {"created": N, "skipped": M}.
    """
    repo = AbacPolicyRepository(db)
    existing = await repo.list_by_tenant(tenant_id)
    existing_names = {p.name for p in existing}
    is_sqlite = bool(db.bind and db.bind.dialect.name == "sqlite")
    next_policy_id: int | None = None
    if is_sqlite:
        max_id = await db.scalar(select(func.max(AbacPolicy.id)))
        next_policy_id = int(max_id or 0) + 1

    created = 0
    skipped = 0
    for policy_def in DEFAULT_ABAC_POLICIES:
        if policy_def["name"] in existing_names:
            skipped += 1
            continue
        policy_kwargs = {
            "tenant_id": tenant_id,
            "name": policy_def["name"],
            "description": policy_def["description"],
            "resource_type": policy_def["resource_type"],
            "action": policy_def["action"],
            "expression": policy_def["expression"],
            "status": "active",
        }
        if next_policy_id is not None:
            policy_kwargs["id"] = next_policy_id
            next_policy_id += 1
        policy = AbacPolicy(**policy_kwargs)
        await repo.create(policy)
        created += 1
    return {"created": created, "skipped": skipped}
