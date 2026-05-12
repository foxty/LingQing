"""Unit tests locking that the SSO bind allowlist is sourced from the tenant's
login domains, NOT from a per-provider field.
"""

from types import SimpleNamespace

import pytest

from apps.tenant_app_service.sso.login_service import SsoLoginService


@pytest.mark.asyncio
async def test_tenant_login_domains_reads_from_tenant_domains():
    """_tenant_login_domains returns the domains on the tenant's login-domain rows."""
    service = SsoLoginService(db=None)

    async def _list_login_domain_names(tenant_id):
        return ["company.com", "subsidiary.com"]

    service.db = SimpleNamespace()
    from apps.tenant_app_service.identity import services as identity_services

    original = identity_services.IdentityAdminService

    class _FakeIdentityAdmin:
        def __init__(self, db):
            pass

        async def list_login_domain_names(self, tenant_id):
            return await _list_login_domain_names(tenant_id)

    identity_services.IdentityAdminService = _FakeIdentityAdmin
    try:
        domains = await service._tenant_login_domains(tenant_id=1)
        assert domains == ["company.com", "subsidiary.com"]
    finally:
        identity_services.IdentityAdminService = original


@pytest.mark.asyncio
async def test_tenant_login_domains_empty_when_tenant_has_none():
    """No tenant login domains => empty allowlist => bind deny-all."""
    service = SsoLoginService(db=None)
    service.db = SimpleNamespace()
    from apps.tenant_app_service.identity import services as identity_services

    original = identity_services.IdentityAdminService

    class _FakeIdentityAdmin:
        def __init__(self, db):
            pass

        async def list_login_domain_names(self, tenant_id):
            return []

    identity_services.IdentityAdminService = _FakeIdentityAdmin
    try:
        domains = await service._tenant_login_domains(tenant_id=1)
        assert domains == []
    finally:
        identity_services.IdentityAdminService = original


def test_provider_response_dto_has_no_allowed_email_domains():
    from apps.tenant_app_service.sso.dtos import AuthProviderResponse

    fields = set(AuthProviderResponse.model_fields)
    assert "allowed_email_domains" not in fields


def test_create_provider_request_dto_has_no_allowed_email_domains():
    from apps.tenant_app_service.sso.dtos import CreateAuthProviderRequest

    fields = set(CreateAuthProviderRequest.model_fields)
    assert "allowed_email_domains" not in fields
