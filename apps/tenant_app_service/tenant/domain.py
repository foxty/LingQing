"""Domain models for tenant module."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.shared.domain.base_domain_model import BaseDomainModel


@dataclass
class PortalBranding:
    """Per-tenant portal header and login branding."""

    app_title: str | None = None
    app_subtitle: str | None = None
    page_title: str | None = None
    logo_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PortalBranding":
        if not data:
            return cls()
        return cls(
            app_title=_optional_str(data.get("app_title")),
            app_subtitle=_optional_str(data.get("app_subtitle")),
            page_title=_optional_str(data.get("page_title")),
            logo_path=_optional_str(data.get("logo_path")),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.app_title is not None:
            result["app_title"] = self.app_title
        if self.app_subtitle is not None:
            result["app_subtitle"] = self.app_subtitle
        if self.page_title is not None:
            result["page_title"] = self.page_title
        if self.logo_path is not None:
            result["logo_path"] = self.logo_path
        return result


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


@dataclass
class TenantConfig:
    """Typed tenant configuration stored in tenants.config JSON."""

    llm_defaults: dict[str, Any] | None = None
    portal_branding: PortalBranding = field(default_factory=PortalBranding)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TenantConfig":
        if not data:
            return cls()
        raw_branding = data.get("portal_branding")
        branding_dict = raw_branding if isinstance(raw_branding, dict) else None
        return cls(
            llm_defaults=data.get("llm_defaults"),
            portal_branding=PortalBranding.from_dict(branding_dict),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.llm_defaults is not None:
            result["llm_defaults"] = self.llm_defaults
        branding_dict = self.portal_branding.to_dict()
        if branding_dict:
            result["portal_branding"] = branding_dict
        return result


@dataclass
class TenantDomain(BaseDomainModel):
    """Tenant domain model for multi-tenancy."""

    id: int
    name: str
    slug: str | None
    description: str | None
    config: TenantConfig = field(default_factory=TenantConfig)
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def is_active(self) -> bool:
        return self.status == "active"


@dataclass
class TenantProvisioningError(Exception):
    """Tenant provisioning operation failed."""

    message: str
    operation: str
    tenant_id: int | None = None

    def __str__(self) -> str:
        if self.tenant_id:
            return f"Tenant {self.tenant_id} {self.operation} failed: {self.message}"
        return f"{self.operation} failed: {self.message}"
