"""Unit tests for SsoAdminService._resolve_tenant identifier parsing and the
AUTH_TENANT_NOT_FOUND error contract.
"""

from types import SimpleNamespace

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.tenant_app_service.sso.services import SsoAdminService


def _service_with_identity_repo(identity_repo):
    service = SsoAdminService(db=None)
    service.identity_repo = identity_repo
    return service


@pytest.mark.asyncio
async def test_resolve_by_email_domain_succeeds():
    async def get_domain(d):
        return SimpleNamespace(tenant_id=7, domain=d)

    async def get_tenant(tid):
        return SimpleNamespace(id=tid, name="Acme", slug="acme")

    service = _service_with_identity_repo(
        SimpleNamespace(get_domain=get_domain, get_tenant=get_tenant)
    )
    tenant, identity = await service._resolve_tenant("alice@company.com")
    assert tenant.id == 7
    assert identity == "alice"


@pytest.mark.asyncio
async def test_not_found_by_domain_includes_domain_in_details():
    async def get_domain(d):
        return None

    service = _service_with_identity_repo(SimpleNamespace(get_domain=get_domain, get_tenant=None))
    with pytest.raises(ValidationError) as exc_info:
        await service._resolve_tenant("alice@unknown.com")
    assert exc_info.value.details["code"] == "AUTH_TENANT_NOT_FOUND"
    assert exc_info.value.details["domain"] == "unknown.com"


@pytest.mark.asyncio
async def test_not_found_by_slug_includes_slug_in_details(monkeypatch):
    async def get_by_slug(self, slug):
        return None

    async def get_domain(d):
        return None

    service = _service_with_identity_repo(SimpleNamespace(get_domain=get_domain, get_tenant=None))
    monkeypatch.setattr(
        "apps.tenant_app_service.tenant.repository.TenantRepository.get_by_slug",
        get_by_slug,
    )
    with pytest.raises(ValidationError) as exc_info:
        await service._resolve_tenant("alice@no-such-slug")
    assert exc_info.value.details["code"] == "AUTH_TENANT_NOT_FOUND"
    assert exc_info.value.details["slug"] == "no-such-slug"


@pytest.mark.asyncio
async def test_invalid_identifier_rejected():
    service = _service_with_identity_repo(SimpleNamespace(get_domain=None, get_tenant=None))
    with pytest.raises(ValidationError) as exc_info:
        await service._resolve_tenant("no-at-sign")
    assert exc_info.value.details["code"] == "AUTH_IDENTIFIER_INVALID"


@pytest.mark.asyncio
async def test_resolve_login_methods_omits_native_when_force_sso():
    tenant = SimpleNamespace(id=1, force_sso=True)
    provider = SimpleNamespace(
        id=10,
        enabled=True,
        provider_type="oidc",
        display_name="Google",
        config_json="encrypted",
    )

    async def list_providers(tenant_id):
        return [provider]

    def decrypt_provider_config(p):
        return {"issuer": "https://accounts.google.com"}

    service = SsoAdminService(db=None)
    service.repo = SimpleNamespace(list_providers=list_providers, decrypt_provider_config=decrypt_provider_config)

    methods = await service.resolve_login_methods(tenant)
    assert all(m.type != "native" for m in methods)
    assert len(methods) == 1
    assert methods[0].issuer == "https://accounts.google.com"


@pytest.mark.asyncio
async def test_resolve_tenant_methods_sets_emergency_password_flag():
    tenant = SimpleNamespace(id=1, name="Acme", slug="acme", force_sso=True)

    async def count_break_glass_admins(tenant_id):
        return 1

    async def list_providers(tenant_id):
        return []

    service = SsoAdminService(db=None)
    service.identity_repo = SimpleNamespace(count_break_glass_admins=count_break_glass_admins)
    service.repo = SimpleNamespace(list_providers=list_providers, decrypt_provider_config=lambda p: {})
    async def mock_resolve(identifier):
        return tenant, "alice"

    service._resolve_tenant = mock_resolve

    result = await service.resolve_tenant_methods("alice@acme.com")
    assert result.force_sso is True
    assert result.emergency_password_available is True
    assert result.login_methods == []
