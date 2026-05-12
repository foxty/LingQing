"""Unit tests for SSO DTO enum validation.

Locks that DTOs reject unknown provider_type / first_login_policy / status and
accept the enum members. No DB.
"""

import pytest
from pydantic import ValidationError

from apps.tenant_app_service.sso.domain import (
    POLICY_JIT,
    STATUS_ACTIVE,
    STATUS_PENDING,
    STATUS_REJECTED,
    FirstLoginPolicy,
    IdentityStatus,
    ProviderType,
)
from apps.tenant_app_service.identity.dtos import BreakGlassRequest, PendingIdentityResponse
from apps.tenant_app_service.sso.dtos import (
    AuthProviderResponse,
    CreateAuthProviderRequest,
    LoginMethodDTO,
    ProviderConfigDTO,
    ProviderConfigResponseDTO,
    UpdateAuthProviderRequest,
)


def _config() -> ProviderConfigDTO:
    return ProviderConfigDTO(client_id="cid", issuer="https://idp")


def test_create_request_accepts_oidc_enum():
    req = CreateAuthProviderRequest(display_name="P", provider_type=ProviderType.OIDC, config=_config())
    assert req.provider_type == ProviderType.OIDC


def test_create_request_accepts_oidc_string():
    req = CreateAuthProviderRequest(display_name="P", provider_type="oidc", config=_config())
    assert req.provider_type == ProviderType.OIDC


def test_create_request_rejects_unknown_provider_type():
    with pytest.raises(ValidationError):
        CreateAuthProviderRequest(display_name="P", provider_type="saml", config=_config())


@pytest.mark.parametrize("policy", list(FirstLoginPolicy))
def test_create_request_accepts_all_policies(policy: FirstLoginPolicy):
    req = CreateAuthProviderRequest(display_name="P", config=_config(), first_login_policy=policy)
    assert req.first_login_policy == policy


def test_create_request_rejects_unknown_policy():
    with pytest.raises(ValidationError):
        CreateAuthProviderRequest(display_name="P", config=_config(), first_login_policy="bogus")


def test_update_request_rejects_unknown_policy():
    with pytest.raises(ValidationError):
        UpdateAuthProviderRequest(first_login_policy="bogus")


def test_auth_provider_response_coerces_db_string_to_enum():
    resp = AuthProviderResponse(
        id=1,
        tenant_id=2,
        provider_type="oidc",
        display_name="P",
        enabled=True,
        config=ProviderConfigResponseDTO(
            client_id="c", client_secret_configured=True, issuer="https://i", scopes=[], extra_authorize_params={}
        ),
        first_login_policy="jit_create",
        callback_url="/cb",
    )
    assert resp.provider_type == ProviderType.OIDC
    assert resp.first_login_policy == POLICY_JIT


def test_pending_identity_response_coerces_status_string():
    for s in (STATUS_ACTIVE, STATUS_PENDING, STATUS_REJECTED):
        r = PendingIdentityResponse(
            id=1,
            tenant_id=2,
            provider_id=3,
            provider_display_name="P",
            external_subject="s",
            email=None,
            display_name=None,
            status=s,
            created_at="2026-01-01T00:00:00",
        )
        assert isinstance(r.status, IdentityStatus)


def test_pending_identity_response_rejects_unknown_status():
    with pytest.raises(ValidationError):
        PendingIdentityResponse(
            id=1,
            tenant_id=2,
            provider_id=3,
            provider_display_name="P",
            external_subject="s",
            email=None,
            display_name=None,
            status="bogus",
            created_at="2026-01-01T00:00:00",
        )


def test_login_method_type_is_plain_string():
    # login method type stays a plain string (native vs provider_type); not enum-constrained
    m = LoginMethodDTO(type="native")
    assert m.type == "native"
    m2 = LoginMethodDTO(type="oidc", provider_id=1, display_name="P")
    assert m2.type == "oidc"


def test_enum_values_match_db_strings():
    """Lock that enum str values equal what the DB stores (drift guard)."""
    from apps.shared.external_identity import BindAction

    assert BindAction.LOGIN == "login"
    assert BindAction.JIT_CREATE == "jit_create"
    assert ProviderType.OIDC == "oidc"
    assert FirstLoginPolicy.JIT_CREATE == "jit_create"
    assert FirstLoginPolicy.PENDING_APPROVAL == "pending_approval"
    assert FirstLoginPolicy.REJECT_UNKNOWN == "reject_unknown"
    assert IdentityStatus.ACTIVE == "active"
    assert IdentityStatus.PENDING == "pending"
    assert IdentityStatus.REJECTED == "rejected"


def test_break_glass_request_accepts_bool():
    req = BreakGlassRequest(is_break_glass=True)
    assert req.is_break_glass is True
    req_off = BreakGlassRequest(is_break_glass=False)
    assert req_off.is_break_glass is False


def test_tenant_user_dto_exposes_is_break_glass_default():
    """Lock that TenantUserDTO carries is_break_glass and defaults to False."""
    from apps.tenant_app_service.tenant.schemas import TenantUserDTO

    dto = TenantUserDTO(
        id=1,
        username="alice",
        role="admin",
        tenant_id=2,
        tenant_name="Acme",
        membership_status="active",
    )
    assert dto.is_break_glass is False


def test_force_sso_guard_requires_at_least_one_break_glass():
    """Lock the domain rule force SSO depends on."""
    from apps.tenant_app_service.sso.domain import can_enable_force_sso

    assert can_enable_force_sso(0) is False
    assert can_enable_force_sso(1) is True
    assert can_enable_force_sso(3) is True
