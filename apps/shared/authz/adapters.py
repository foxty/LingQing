"""Adapters for ABAC policies."""

from apps.shared.authz.domain import AbacPolicyDomain
from apps.shared.authz.schemas import AbacPolicyDTO
from apps.shared.db.models import AbacPolicy


def db_abac_policy_to_domain(policy: AbacPolicy) -> AbacPolicyDomain:
    return AbacPolicyDomain(
        id=policy.id,
        tenant_id=policy.tenant_id,
        name=policy.name,
        description=policy.description,
        resource_type=policy.resource_type,
        action=policy.action,
        expression=policy.expression,
        status=policy.status,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
        created_by=policy.created_by,
        updated_by=policy.updated_by,
    )


def domain_abac_policy_to_api(policy: AbacPolicyDomain) -> AbacPolicyDTO:
    return AbacPolicyDTO(**policy.model_dump())
