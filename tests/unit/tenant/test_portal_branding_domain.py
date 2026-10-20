from apps.shared.infra.storage.paths import resolve_storage_ref
from apps.shared.schemas.tenant import tenant_config_dict_to_dto
from apps.tenant_app_service.tenant.domain import PortalBranding, TenantConfig


def test_portal_branding_from_dict_trims_and_drops_empty():
    branding = PortalBranding.from_dict(
        {
            "app_title": "  Acme  ",
            "app_subtitle": "",
            "page_title": None,
            "logo_path": " /data/logo.png ",
        }
    )
    assert branding.app_title == "Acme"
    assert branding.app_subtitle is None
    assert branding.logo_path == "/data/logo.png"


def test_tenant_config_round_trip_includes_portal_branding():
    config = TenantConfig(
        llm_defaults={"agent_profile_id": 1},
        portal_branding=PortalBranding(app_title="Acme", app_subtitle="Workbench"),
    )
    restored = TenantConfig.from_dict(config.to_dict())
    assert restored.portal_branding.app_title == "Acme"
    assert restored.portal_branding.app_subtitle == "Workbench"
    assert restored.llm_defaults == {"agent_profile_id": 1}


def test_tenant_config_dict_to_dto_includes_portal_branding():
    dto = tenant_config_dict_to_dto(
        {
            "portal_branding": {
                "app_title": "Acme",
                "app_subtitle": "Workbench",
                "logo_path": "portal-logo.png",
            },
        }
    )
    assert dto is not None
    assert dto.portal_branding is not None
    assert dto.portal_branding.app_title == "Acme"
    assert dto.portal_branding.logo_url == "/tenants/portal-branding/logo"
    assert dto.llm_defaults is None


def test_resolve_storage_ref_for_portal_logo_key():
    resolved = resolve_storage_ref(1, "portal-logo.png")
    assert resolved.endswith("/tenants/tenant_1/documents/portal-logo.png")
