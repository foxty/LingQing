"""Domain models and business rules for tenant SSO.

Pure business logic: provider entity, identity binding decisions,
domain allowlist, force-SSO/break-glass invariants. No framework deps.

Identity binding rules (decide_bind, ExtractedIdentity, BindDecision,
IdentityStatus, FirstLoginPolicy) now live in the shared platform kernel
`apps.shared.external_identity.domain` and are re-exported here for backward
compatibility with existing SSO call sites and tests.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from apps.shared.core.exceptions import ValidationError
from apps.shared.external_identity.domain import (
    POLICY_JIT,
    POLICY_PENDING,
    POLICY_REJECT,
    STATUS_ACTIVE,
    STATUS_PENDING,
    STATUS_REJECTED,
    BindDecision,
    ExistingIdentityMatch,
    ExistingUserMatch,
    ExtractedIdentity,
    FirstLoginPolicy,
    IdentityStatus,
    decide_bind,
    email_domain_allowed,
    validate_policy,
)

__all__ = [
    "POLICY_JIT",
    "POLICY_PENDING",
    "POLICY_REJECT",
    "STATUS_ACTIVE",
    "STATUS_PENDING",
    "STATUS_REJECTED",
    "BindDecision",
    "ExistingIdentityMatch",
    "ExistingUserMatch",
    "ExtractedIdentity",
    "FirstLoginPolicy",
    "IdentityStatus",
    "decide_bind",
    "email_domain_allowed",
    "validate_policy",
    "ProviderType",
    "ProviderConfig",
    "ProviderDomain",
    "validate_provider_type",
    "LOGIN_METHOD_NATIVE",
    "can_enable_force_sso",
]


class ProviderType(enum.StrEnum):
    """Supported identity provider types. v1 ships OIDC only."""

    OIDC = "oidc"


SUPPORTED_PROVIDER_TYPES: frozenset[ProviderType] = frozenset(ProviderType)

# Backward-compatible string constants (enum members are str instances).
PROVIDER_TYPE_OIDC: ProviderType = ProviderType.OIDC
LOGIN_METHOD_NATIVE = "native"

DEFAULT_JIT_ROLE = "viewer"


@dataclass
class ProviderConfig:
    """Typed view of an auth_providers.config_json (decrypted)."""

    client_id: str
    client_secret: str
    issuer: str
    scopes: list[str] = field(default_factory=lambda: ["openid", "email", "profile"])
    extra_authorize_params: dict[str, str] = field(default_factory=dict)
    # Optional explicit endpoint overrides (skip discovery when all four set)
    authorize_endpoint: str | None = None
    token_endpoint: str | None = None
    userinfo_endpoint: str | None = None
    jwks_uri: str | None = None


@dataclass
class ProviderDomain:
    """An auth provider row in domain form."""

    id: int
    tenant_id: int
    provider_type: str
    display_name: str
    enabled: bool
    config: ProviderConfig
    first_login_policy: str


def validate_provider_type(provider_type: str) -> None:
    """Fail closed on unknown provider types."""
    if provider_type not in SUPPORTED_PROVIDER_TYPES:
        raise ValidationError(
            f"Unsupported provider_type: {provider_type}",
            {"code": "SSO_UNSUPPORTED_PROVIDER_TYPE"},
        )


from apps.tenant_app_service.identity.domain import can_enable_force_sso  # noqa: E402
