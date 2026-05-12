"""Shared cross-domain type aliases."""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

RESOURCE_TYPE_DOCUMENT: Final = "document"
RESOURCE_TYPE_DOCUMENT_COLLECTION: Final = "document_collection"
RESOURCE_TYPE_ASSET: Final = "asset"
RESOURCE_TYPE_USER: Final = "user"
RESOURCE_TYPE_API_CONNECTOR: Final = "api_connector"
RESOURCE_TYPE_DATA_SOURCE: Final = "data_source"
RESOURCE_TYPE_DASHBOARD: Final = "dashboard"
RESOURCE_TYPE_REPORT: Final = "report"
RESOURCE_TYPE_SCHEDULED_TASK: Final = "scheduled_task"
RESOURCE_TYPE_APP: Final = "app"
RESOURCE_TYPE_AGENT: Final = "agent"

# Canonical search targets for /search endpoint query parameter.
SEARCH_TARGET_DOCUMENT: Final = "document"
SEARCH_TARGET_ASSET: Final = "asset"
SEARCH_TARGET_API_CONNECTOR: Final = "api_connector"
SEARCH_TARGET_BOTH: Final = "both"

AUTHZ_ACTION_READ: Final = "read"
AUTHZ_ACTION_WRITE: Final = "write"
AUTHZ_ACTION_MANAGE: Final = "manage"

# Keep ABAC constants as compatibility aliases.
ABAC_ACTION_READ = AUTHZ_ACTION_READ
ABAC_ACTION_WRITE = AUTHZ_ACTION_WRITE

# Keep ACL constants as explicit aliases for readability at call sites.
ACL_PERMISSION_READ = AUTHZ_ACTION_READ
ACL_PERMISSION_WRITE = AUTHZ_ACTION_WRITE
ACL_PERMISSION_MANAGE = AUTHZ_ACTION_MANAGE
ACL_PRINCIPAL_USER: Final = "user"
ACL_PRINCIPAL_ROLE: Final = "role"
ACL_EFFECT_ALLOW: Final = "allow"
ACL_EFFECT_DENY: Final = "deny"

ResourceType: TypeAlias = Literal[
    "document",
    "document_collection",
    "asset",
    "user",
    "api_connector",
    "data_source",
    "agent",
]
AclShareResourceType: TypeAlias = Literal[
    ResourceType,
    "dashboard",
    "report",
    "scheduled_task",
    "app",
]
AuthzAction: TypeAlias = Literal["read", "write", "manage"]
AbacAction = AuthzAction
AclPermission = AuthzAction

AUTHZ_ACTIONS: tuple[AuthzAction, ...] = (
    AUTHZ_ACTION_READ,
    AUTHZ_ACTION_WRITE,
    AUTHZ_ACTION_MANAGE,
)

# Compatibility aliases for legacy ABAC/ACL call sites.
ABAC_ACTIONS: tuple[AbacAction, ...] = AUTHZ_ACTIONS
ACL_PERMISSIONS: tuple[AclPermission, ...] = AUTHZ_ACTIONS


def normalize_authz_action(action: str) -> AuthzAction:
    normalized = action.strip().lower()
    if normalized not in AUTHZ_ACTIONS:
        raise ValueError(f"Unsupported authorization action: {action}")
    return normalized  # type: ignore[return-value]


def to_abac_action(action: str) -> AbacAction:
    normalized = normalize_authz_action(action)
    if normalized == AUTHZ_ACTION_MANAGE:
        return ABAC_ACTION_WRITE
    return normalized  # type: ignore[return-value]


def required_acl_permissions(action: str) -> tuple[AclPermission, ...]:
    normalized = normalize_authz_action(action)
    if normalized == AUTHZ_ACTION_READ:
        return (ACL_PERMISSION_READ, ACL_PERMISSION_WRITE, ACL_PERMISSION_MANAGE)
    if normalized == AUTHZ_ACTION_WRITE:
        return (ACL_PERMISSION_WRITE, ACL_PERMISSION_MANAGE)
    return (ACL_PERMISSION_MANAGE,)


SearchableResourceType: TypeAlias = Literal["document", "asset", "api_connector"]
IndexSourceType: TypeAlias = Literal["document", "asset", "api_connector"]
SearchTargetType: TypeAlias = Literal["document", "asset", "api_connector", "both"]

SEARCHABLE_RESOURCE_TYPES: tuple[SearchableResourceType, ...] = (
    RESOURCE_TYPE_DOCUMENT,
    RESOURCE_TYPE_ASSET,
)
ACL_SHARE_RESOURCE_TYPES: tuple[AclShareResourceType, ...] = (
    RESOURCE_TYPE_DOCUMENT_COLLECTION,
    RESOURCE_TYPE_API_CONNECTOR,
    RESOURCE_TYPE_DATA_SOURCE,
    RESOURCE_TYPE_DASHBOARD,
    RESOURCE_TYPE_REPORT,
    RESOURCE_TYPE_SCHEDULED_TASK,
    RESOURCE_TYPE_APP,
    RESOURCE_TYPE_AGENT,
)
INDEX_SOURCE_TYPES: tuple[IndexSourceType, ...] = (
    RESOURCE_TYPE_DOCUMENT,
    RESOURCE_TYPE_ASSET,
    RESOURCE_TYPE_API_CONNECTOR,
)
SEARCH_TARGET_TYPES: tuple[SearchTargetType, ...] = (
    SEARCH_TARGET_DOCUMENT,
    SEARCH_TARGET_ASSET,
    SEARCH_TARGET_API_CONNECTOR,
    SEARCH_TARGET_BOTH,
)
