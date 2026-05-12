"""ABAC policy router."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.adapters import domain_abac_policy_to_api
from apps.shared.authz.dsl import (
    DslParseError,
    DslValidationError,
    build_attr_registry,
    expr_to_human,
    parse_dsl,
    validate_expr,
)
from apps.shared.authz.schemas import (
    AbacPolicyCreateRequest,
    AbacPolicyDTO,
    AbacPolicySeedResponse,
    AbacPolicySimulateRequest,
    AbacPolicySimulateResponse,
    AbacPolicyUpdateRequest,
    AbacPolicyValidateRequest,
    AbacPolicyValidateResponse,
)
from apps.shared.authz.service import AbacPolicyService
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.core.exceptions import ValidationError
from apps.shared.db.session import get_db
from apps.shared.domain.types import AbacAction, ResourceType
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/abac", tags=["abac"], include_in_schema=False)


def _service(db: AsyncSession, tenant_id: int) -> AbacPolicyService:
    return AbacPolicyService.create(tenant_id, db)


# ---------------------------------------------------------------------------
# Validate
# ---------------------------------------------------------------------------


@router.post("/policies/validate", response_model=AbacPolicyValidateResponse)
async def validate_expression(
    payload: AbacPolicyValidateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_READ)),
):
    """Stateless expression validation — no DB access."""
    if not payload.expression or not payload.expression.strip():
        return AbacPolicyValidateResponse(valid=False, errors=["Expression cannot be empty."], human_readable=None)
    registry = build_attr_registry({"resource.id", "resource.owner_id"})
    try:
        parsed = parse_dsl(payload.expression)
        validate_expr(parsed, registry)
        return AbacPolicyValidateResponse(valid=True, errors=[], human_readable=expr_to_human(parsed))
    except (DslParseError, DslValidationError) as exc:
        return AbacPolicyValidateResponse(valid=False, errors=[str(exc)], human_readable=None)


# ---------------------------------------------------------------------------
# Simulate
# ---------------------------------------------------------------------------


@router.post("/policies/simulate", response_model=AbacPolicySimulateResponse)
async def simulate_policy(
    payload: AbacPolicySimulateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate a single expression against real DB data for a specific resource."""
    service = _service(db, current_user.tenant_id)
    try:
        allowed, reason = await service.simulate_policy(
            expression=payload.expression,
            resource_type=payload.resource_type,
            action=payload.action,
            user_id=payload.user_id,
            user_role=payload.user_role,
            resource_id=payload.resource_id,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return AbacPolicySimulateResponse(allowed=allowed, reason=reason)


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------


@router.post("/policies/seed", response_model=AbacPolicySeedResponse)
async def seed_policies(
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    """Idempotent seed of default ABAC policies for the tenant."""
    from apps.shared.core.policy_seed import seed_default_policies

    result = await seed_default_policies(db, current_user.tenant_id)
    return AbacPolicySeedResponse(**result)


# ---------------------------------------------------------------------------
# Enable / Disable
# ---------------------------------------------------------------------------


@router.patch("/policies/{policy_id}/enable", response_model=AbacPolicyDTO)
async def enable_abac_policy(
    policy_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db, current_user.tenant_id)
    policy = await service.enable_policy(policy_id, updated_by=current_user.id)
    return domain_abac_policy_to_api(policy)


@router.patch("/policies/{policy_id}/disable", response_model=AbacPolicyDTO)
async def disable_abac_policy(
    policy_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db, current_user.tenant_id)
    policy = await service.disable_policy(policy_id, updated_by=current_user.id)
    return domain_abac_policy_to_api(policy)


# ---------------------------------------------------------------------------
# CRUD (migrated from tags.py)
# ---------------------------------------------------------------------------


@router.get("/policies", response_model=list[AbacPolicyDTO])
async def list_abac_policies(
    resource_type: ResourceType | None = Query(default=None),
    action: AbacAction | None = Query(default=None),
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db, current_user.tenant_id)
    policies = await service.list_policies(resource_type=resource_type, action=action)
    return [domain_abac_policy_to_api(policy) for policy in policies]


@router.post("/policies", response_model=AbacPolicyDTO)
async def create_abac_policy(
    payload: AbacPolicyCreateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db, current_user.tenant_id)
    policy = await service.create_policy(
        name=payload.name,
        description=payload.description,
        resource_type=payload.resource_type,
        action=payload.action,
        expression=payload.expression,
        created_by=current_user.id,
    )
    return domain_abac_policy_to_api(policy)


@router.get("/policies/{policy_id}", response_model=AbacPolicyDTO)
async def get_abac_policy(
    policy_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_READ)),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db, current_user.tenant_id)
    policy = await service.get_policy(policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return domain_abac_policy_to_api(policy)


@router.patch("/policies/{policy_id}", response_model=AbacPolicyDTO)
async def update_abac_policy(
    policy_id: int,
    payload: AbacPolicyUpdateRequest,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db, current_user.tenant_id)
    policy = await service.update_policy(
        policy_id=policy_id,
        name=payload.name,
        description=payload.description,
        resource_type=payload.resource_type,
        action=payload.action,
        expression=payload.expression,
        updated_by=current_user.id,
    )
    return domain_abac_policy_to_api(policy)


@router.delete("/policies/{policy_id}", status_code=204)
async def delete_abac_policy(
    policy_id: int,
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
    db: AsyncSession = Depends(get_db),
):
    service = _service(db, current_user.tenant_id)
    await service.delete_policy(policy_id)
