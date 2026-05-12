"""Authorization (RBAC/ABAC) module exports."""

from apps.shared.authz.adapters import domain_abac_policy_to_api
from apps.shared.authz.authz_query_builder import AuthzSqlFilter
from apps.shared.authz.domain import AbacPolicyDomain
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
from apps.shared.authz.ta_permissions import TA_ALL_PERMISSIONS, TenantAppPermissions, is_known_ta_permission
from apps.shared.authz.ta_rbac import DEFAULT_ROLE_PERMISSIONS, EffectiveRBAC, get_effective_rbac, role_has_permission
from apps.shared.authz.tm_permissions import TM_ALL_PERMISSIONS, TenantManagerPermissions, is_known_tm_permission
from apps.shared.authz.tm_rbac import PLATFORM_ROLES, TM_ROLE_PERMISSIONS, role_has_tm_permission

__all__ = [
    "AbacPolicyDomain",
    "AbacPolicyDTO",
    "AbacPolicyCreateRequest",
    "AbacPolicyUpdateRequest",
    "AbacPolicyValidateRequest",
    "AbacPolicyValidateResponse",
    "AbacPolicySimulateRequest",
    "AbacPolicySimulateResponse",
    "AbacPolicySeedResponse",
    "AbacPolicyService",
    "AuthzSqlFilter",
    "TenantAppPermissions",
    "TA_ALL_PERMISSIONS",
    "is_known_ta_permission",
    "TenantManagerPermissions",
    "TM_ALL_PERMISSIONS",
    "is_known_tm_permission",
    "DEFAULT_ROLE_PERMISSIONS",
    "EffectiveRBAC",
    "get_effective_rbac",
    "role_has_permission",
    "PLATFORM_ROLES",
    "TM_ROLE_PERMISSIONS",
    "role_has_tm_permission",
    "domain_abac_policy_to_api",
]
