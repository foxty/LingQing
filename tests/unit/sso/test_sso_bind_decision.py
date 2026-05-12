"""Unit tests for the SSO bind decision (pure, no DB).

Locks the callback bind algorithm so later adapters cannot silently change
behavior. Each test is an invariant of `decide_bind`.
"""

import pytest

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
    decide_bind,
    email_domain_allowed,
    validate_policy,
)
from apps.tenant_app_service.sso.domain import (
    can_enable_force_sso,
    validate_provider_type,
)

ALLOWED = ["company.com"]
EXTRACTED = ExtractedIdentity(external_subject="sub-1", email="alice@company.com", display_name="Alice")


def _decide(**overrides) -> BindDecision:
    kwargs = dict(
        extracted=EXTRACTED,
        allowed_domains=ALLOWED,
        subject_match=None,
        email_match=None,
        policy=POLICY_JIT,
    )
    kwargs.update(overrides)
    return decide_bind(**kwargs)


# ---------- Domain allowlist ----------


def test_email_domain_allowed_matches():
    assert email_domain_allowed("alice@company.com", ["company.com"]) is True


def test_email_domain_allowed_case_insensitive():
    assert email_domain_allowed("Alice@Company.COM", ["company.com"]) is True


def test_email_domain_allowed_rejects_other_domain():
    assert email_domain_allowed("alice@other.com", ["company.com"]) is False


def test_email_domain_allowed_rejects_empty_email():
    assert email_domain_allowed(None, ["company.com"]) is False
    assert email_domain_allowed("", ["company.com"]) is False


def test_email_domain_allowed_rejects_when_allowlist_empty():
    # Empty allowlist = deny-all (safer default for SSO)
    assert email_domain_allowed("alice@company.com", []) is False


# ---------- Subject hit ----------


def test_subject_hit_active_logs_in():
    match = ExistingIdentityMatch(identity_id=1, user_id=42, status=STATUS_ACTIVE)
    decision = _decide(subject_match=match)
    assert decision.action == "login"
    assert decision.user_id == 42


def test_subject_hit_pending_waits():
    match = ExistingIdentityMatch(identity_id=1, user_id=None, status=STATUS_PENDING)
    decision = _decide(subject_match=match)
    assert decision.action == "pending"
    assert decision.reason == "subject_pending"


def test_subject_hit_rejected_denies():
    match = ExistingIdentityMatch(identity_id=1, user_id=42, status=STATUS_REJECTED)
    decision = _decide(subject_match=match)
    assert decision.action == "deny"
    assert decision.reason == "subject_rejected"


# ---------- Email attach ----------


def test_unique_email_attaches_to_existing_user():
    match = ExistingUserMatch(user_id=42, count=1)
    decision = _decide(email_match=match)
    assert decision.action == "attach"
    assert decision.user_id == 42


def test_email_collision_two_members_goes_pending():
    match = ExistingUserMatch(user_id=42, count=2)
    decision = _decide(email_match=match)
    assert decision.action == "pending"
    assert decision.reason == "email_collision"


# ---------- First-login policy ----------


def test_jit_create_creates_user():
    decision = _decide(policy=POLICY_JIT)
    assert decision.action == "jit_create"


def test_pending_approval_stores_pending():
    decision = _decide(policy=POLICY_PENDING)
    assert decision.action == "pending"
    assert decision.reason == "policy_pending_approval"


def test_reject_unknown_denies():
    decision = _decide(policy=POLICY_REJECT)
    assert decision.action == "deny"
    assert decision.reason == "policy_reject_unknown"


# ---------- Domain reject before bind ----------


def test_domain_not_allowed_denies_before_subject_hit():
    # Even with a subject hit, a domain mismatch denies
    match = ExistingIdentityMatch(identity_id=1, user_id=42, status=STATUS_ACTIVE)
    decision = decide_bind(
        extracted=ExtractedIdentity(external_subject="sub-1", email="alice@other.com", display_name="Alice"),
        allowed_domains=ALLOWED,
        subject_match=match,
        email_match=None,
        policy=POLICY_JIT,
    )
    assert decision.action == "deny"
    assert decision.reason == "domain_not_allowed"


def test_missing_email_denies():
    decision = decide_bind(
        extracted=ExtractedIdentity(external_subject="sub-1", email=None, display_name="Alice"),
        allowed_domains=ALLOWED,
        subject_match=None,
        email_match=None,
        policy=POLICY_JIT,
    )
    # domain check runs first and rejects empty email as not-allowed
    assert decision.action == "deny"
    assert decision.reason == "domain_not_allowed"


# ---------- Validation ----------


def test_validate_provider_type_rejects_unknown():
    with pytest.raises(Exception):
        validate_provider_type("saml")


def test_validate_provider_type_accepts_oidc():
    validate_provider_type("oidc")  # should not raise


def test_validate_policy_rejects_unknown():
    with pytest.raises(Exception):
        validate_policy("bogus")


# ---------- Force SSO ----------


@pytest.mark.parametrize(
    "count,expected",
    [
        (0, False),
        (1, True),
        (2, True),
    ],
)
def test_can_enable_force_sso(count, expected):
    assert can_enable_force_sso(count) is expected
