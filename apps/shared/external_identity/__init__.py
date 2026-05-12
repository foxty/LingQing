"""External identity platform kernel.

Shared domain rules, repository, and application service for binding
external IdP/channel subjects (OIDC sub, Slack user id, WeCom userid, etc.)
to internal LingQing users. Consumed by feature modules like `sso/` and
`slack/` — never imports them.
"""

from apps.shared.external_identity.domain import (
    POLICY_JIT,
    POLICY_PENDING,
    POLICY_REJECT,
    SOURCE_KIND_CHANNEL_WORKSPACE,
    SOURCE_KIND_LOGIN_PROVIDER,
    STATUS_ACTIVE,
    STATUS_PENDING,
    STATUS_REJECTED,
    BindAction,
    BindDecision,
    ExistingIdentityMatch,
    ExistingUserMatch,
    ExtractedIdentity,
    FirstLoginPolicy,
    IdentityBindingPort,
    IdentityBindingResult,
    IdentitySourceKind,
    IdentityStatus,
    decide_bind,
    email_domain_allowed,
    login_provider_source_key,
    slack_workspace_source_key,
    validate_policy,
)
from apps.shared.external_identity.service import IdentityBindingService

__all__ = [
    "BindAction",
    "BindDecision",
    "ExistingIdentityMatch",
    "ExistingUserMatch",
    "ExtractedIdentity",
    "FirstLoginPolicy",
    "IdentityBindingPort",
    "IdentityBindingResult",
    "IdentityBindingService",
    "IdentitySourceKind",
    "IdentityStatus",
    "POLICY_JIT",
    "SOURCE_KIND_CHANNEL_WORKSPACE",
    "SOURCE_KIND_LOGIN_PROVIDER",
    "login_provider_source_key",
    "slack_workspace_source_key",
    "POLICY_PENDING",
    "POLICY_REJECT",
    "STATUS_ACTIVE",
    "STATUS_PENDING",
    "STATUS_REJECTED",
    "decide_bind",
    "email_domain_allowed",
    "validate_policy",
]
