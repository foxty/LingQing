"""Domain layer for external identity binding.

Pure business logic: identity status, first-login policy, the bind
decision algorithm, and the IdentityBindingPort protocol. No framework
or persistence imports — innermost core.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Protocol

from apps.shared.core.exceptions import ValidationError


class FirstLoginPolicy(enum.StrEnum):
    """Policy applied when an external identity does not match an existing user."""

    JIT_CREATE = "jit_create"
    PENDING_APPROVAL = "pending_approval"
    REJECT_UNKNOWN = "reject_unknown"


class IdentityStatus(enum.StrEnum):
    """Lifecycle status of an external identity row."""

    ACTIVE = "active"
    PENDING = "pending"
    REJECTED = "rejected"


SUPPORTED_POLICIES: frozenset[FirstLoginPolicy] = frozenset(FirstLoginPolicy)

# Backward-compatible string constants (enum members are str instances).
POLICY_JIT: FirstLoginPolicy = FirstLoginPolicy.JIT_CREATE
POLICY_PENDING: FirstLoginPolicy = FirstLoginPolicy.PENDING_APPROVAL
POLICY_REJECT: FirstLoginPolicy = FirstLoginPolicy.REJECT_UNKNOWN
STATUS_ACTIVE: IdentityStatus = IdentityStatus.ACTIVE
STATUS_PENDING: IdentityStatus = IdentityStatus.PENDING
STATUS_REJECTED: IdentityStatus = IdentityStatus.REJECTED

DEFAULT_JIT_ROLE = "viewer"


class BindAction(enum.StrEnum):
    """Outcome of a bind decision or binding service call."""

    LOGIN = "login"
    ATTACH = "attach"
    JIT_CREATE = "jit_create"
    PENDING = "pending"
    DENY = "deny"


class IdentitySourceKind(enum.StrEnum):
    """Kind of external identity source within a tenant."""

    LOGIN_PROVIDER = "login_provider"
    CHANNEL_WORKSPACE = "channel_workspace"


SUPPORTED_SOURCE_KINDS: frozenset[IdentitySourceKind] = frozenset(IdentitySourceKind)

SOURCE_KIND_LOGIN_PROVIDER: IdentitySourceKind = IdentitySourceKind.LOGIN_PROVIDER
SOURCE_KIND_CHANNEL_WORKSPACE: IdentitySourceKind = IdentitySourceKind.CHANNEL_WORKSPACE


def login_provider_source_key(auth_provider_id: int) -> str:
    """Stable source_key for an OIDC/SAML login provider row."""
    return f"oidc:{auth_provider_id}"


def slack_workspace_source_key(*, team_id: str | None, tenant_id: int) -> str:
    """Stable source_key for a Slack workspace within a tenant."""
    scope = team_id or f"tenant:{tenant_id}"
    return f"slack:{scope}"


def is_slack_tenant_placeholder_source_key(source_key: str, tenant_id: int) -> bool:
    """True for provisional slack:tenant:{id} rows created before a team id is known."""
    return source_key == slack_workspace_source_key(team_id=None, tenant_id=tenant_id)


def slack_team_id_from_source_key(source_key: str) -> str | None:
    """Extract Slack team id from slack:{team_id}; None for tenant placeholders."""
    prefix = "slack:"
    if not source_key.startswith(prefix):
        return None
    scope = source_key[len(prefix) :]
    if scope.startswith("tenant:"):
        return None
    return scope


@dataclass
class ExtractedIdentity:
    """Standardized identity extracted from an IdP/channel callback."""

    external_subject: str
    email: str | None
    display_name: str | None


@dataclass
class ExistingIdentityMatch:
    """Result of looking up an existing external_identity by subject."""

    identity_id: int
    user_id: int | None
    status: str


@dataclass
class ExistingUserMatch:
    """Result of looking up an existing tenant member by email."""

    user_id: int
    count: int  # number of members sharing this email; >1 means ambiguous


@dataclass
class BindDecision:
    """Decision returned by decide_bind for an external identity callback."""

    action: BindAction
    user_id: int | None = None
    reason: str | None = None


@dataclass
class IdentityBindingResult:
    """Outcome of IdentityBindingService.resolve_or_bind.

    user_id is set when an internal user is resolved (login/attach/jit_create);
    identity_id is the external_identities row id when one was created or updated.
    """

    action: BindAction
    user_id: int | None = None
    identity_id: int | None = None
    reason: str | None = None


class IdentityBindingPort(Protocol):
    """Port for the shared identity binding application service.

    Channels (sso/, slack/, future wecom/) depend on this narrow, stable API
    instead of duplicating bind orchestration. Implementations must NOT
    import channel modules.
    """

    async def resolve_or_bind(
        self,
        *,
        tenant_id: int,
        identity_source_id: int,
        extracted: ExtractedIdentity,
        allowed_domains: list[str],
        policy: str,
    ) -> IdentityBindingResult: ...

    async def approve_pending(
        self,
        *,
        tenant_id: int,
        identity_id: int,
        user_id: int | None = None,
    ) -> IdentityBindingResult: ...

    async def reject_pending(self, *, tenant_id: int, identity_id: int) -> IdentityBindingResult: ...

    async def list_pending(self, *, tenant_id: int) -> list[IdentityBindingResult]: ...

    async def get_active_binding(
        self,
        *,
        tenant_id: int,
        identity_source_id: int,
        external_subject: str,
    ) -> IdentityBindingResult | None: ...


def validate_policy(policy: str) -> None:
    """Fail closed on unknown first-login policies."""
    if policy not in SUPPORTED_POLICIES:
        raise ValidationError(
            f"Unsupported first_login_policy: {policy}",
            {"code": "IDENTITY_UNSUPPORTED_POLICY"},
        )


def email_domain_allowed(email: str | None, allowed_domains: list[str]) -> bool:
    """True if email's domain is in the allowlist.

    Empty allowlist means deny-all (safer default). An empty email
    can never match.
    """
    if not email or "@" not in email:
        return False
    if not allowed_domains:
        return False
    domain = email.rsplit("@", 1)[1].lower()
    return domain in {d.lower() for d in allowed_domains}


def decide_bind(
    *,
    extracted: ExtractedIdentity,
    allowed_domains: list[str],
    subject_match: ExistingIdentityMatch | None,
    email_match: ExistingUserMatch | None,
    policy: str,
) -> BindDecision:
    """Pure bind decision for an external identity callback.

    Order (tenant-scoped, all inputs already scoped to one tenant):
      1. Domain allowlist check (deny first).
      2. Subject hit -> reuse user (active login / pending wait / rejected deny).
      3. Unique email hit -> attach to that user.
      4. Apply first-login policy.

    Email is a helper for attach, not the identity primary key. The stable
    key is (tenant_id, identity_source_id, external_subject). Two members sharing
    the same email -> no auto-attach, goes pending.
    """
    # 1. Domain allowlist (reject before any bind)
    if not email_domain_allowed(extracted.email, allowed_domains):
        return BindDecision(action=BindAction.DENY, reason="domain_not_allowed")

    # Missing email cannot attach or JIT (no way to identify the user)
    if not extracted.email:
        return BindDecision(action=BindAction.DENY, reason="missing_email")

    # 2. Subject hit
    if subject_match is not None:
        if subject_match.status == STATUS_ACTIVE:
            return BindDecision(action=BindAction.LOGIN, user_id=subject_match.user_id)
        if subject_match.status == STATUS_PENDING:
            return BindDecision(action=BindAction.PENDING, reason="subject_pending")
        # rejected or unknown status
        return BindDecision(action=BindAction.DENY, reason="subject_rejected")

    # 3. Unique email attach
    if email_match is not None:
        if email_match.count == 1:
            return BindDecision(action=BindAction.ATTACH, user_id=email_match.user_id)
        # ambiguous: two members share the same email -> admin must decide
        return BindDecision(action=BindAction.PENDING, reason="email_collision")

    # 4. First-login policy
    if policy == POLICY_JIT:
        return BindDecision(action=BindAction.JIT_CREATE)
    if policy == POLICY_PENDING:
        return BindDecision(action=BindAction.PENDING, reason="policy_pending_approval")
    if policy == POLICY_REJECT:
        return BindDecision(action=BindAction.DENY, reason="policy_reject_unknown")

    # Should be unreachable due to validate_policy at write time
    return BindDecision(action=BindAction.DENY, reason="unsupported_policy")
