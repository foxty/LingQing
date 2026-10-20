"""Shared DTOs for tenant domain."""

from pydantic import BaseModel, Field

# Relative API path returned on PortalBrandingDTO when config stores logo_path (authenticated).
PORTAL_BRANDING_AUTHENTICATED_LOGO_PATH = "/tenants/portal-branding/logo"


def public_portal_branding_logo_path(slug: str) -> str:
    return f"/public/tenants/{slug}/portal-branding/logo"


class LLMDefaultsDTO(BaseModel):
    agent_profile_id: int | None = None
    mini_agent_profile_id: int | None = None
    embedding_profile_id: int | None = None


class PortalBrandingDTO(BaseModel):
    """Portal header/login branding for a tenant."""

    app_title: str | None = Field(default=None, max_length=80)
    app_subtitle: str | None = Field(default=None, max_length=120)
    page_title: str | None = Field(default=None, max_length=120)
    logo_url: str | None = Field(
        default=None,
        description="Relative API path to tenant logo, when configured",
    )


class UpdatePortalBrandingRequest(BaseModel):
    """Partial update for portal branding text fields (logo uses upload endpoint)."""

    app_title: str | None = Field(default=None, max_length=80)
    app_subtitle: str | None = Field(default=None, max_length=120)
    page_title: str | None = Field(default=None, max_length=120)


class TenantConfigDTO(BaseModel):
    """Tenant configuration aggregate."""

    llm_defaults: LLMDefaultsDTO | None = Field(default=None, description="Default model profile IDs")
    portal_branding: PortalBrandingDTO | None = Field(
        default=None,
        description=(
            "Portal header branding text fields from JSON. "
            "logo_url is the authenticated logo API path when logo_path is stored; "
            "use GET /tenants/portal-branding for the full branding payload."
        ),
    )


def tenant_config_dict_to_dto(config: dict | None) -> TenantConfigDTO | None:
    """Map persisted tenants.config JSON to TenantConfigDTO (all known sections).

    Persisted branding uses logo_path; logo_url is derived for API consumers.
    """
    if not config:
        return None

    llm_defaults: LLMDefaultsDTO | None = None
    raw_llm = config.get("llm_defaults")
    if isinstance(raw_llm, dict):
        llm_defaults = LLMDefaultsDTO(**raw_llm)

    portal_branding: PortalBrandingDTO | None = None
    raw_branding = config.get("portal_branding")
    if isinstance(raw_branding, dict):
        logo_path = raw_branding.get("logo_path")
        has_logo = isinstance(logo_path, str) and bool(logo_path.strip())
        portal_branding = PortalBrandingDTO(
            app_title=raw_branding.get("app_title"),
            app_subtitle=raw_branding.get("app_subtitle"),
            page_title=raw_branding.get("page_title"),
            logo_url=PORTAL_BRANDING_AUTHENTICATED_LOGO_PATH if has_logo else None,
        )

    if llm_defaults is None and portal_branding is None:
        return None

    return TenantConfigDTO(llm_defaults=llm_defaults, portal_branding=portal_branding)


class TenantDTO(BaseModel):
    """Tenant DTO."""

    id: int
    name: str
    slug: str
    description: str
    config: TenantConfigDTO | None = Field(
        default=None,
        description="Tenant configuration (optional, may be excluded for list views)",
    )
