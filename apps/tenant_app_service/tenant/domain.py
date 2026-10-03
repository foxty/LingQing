"""Domain models for tenant module."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.shared.domain.base_domain_model import BaseDomainModel


@dataclass
class TenantConfig:
    """Typed tenant configuration stored in tenants.config JSON."""

    llm_defaults: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TenantConfig":
        if not data:
            return cls()
        return cls(llm_defaults=data.get("llm_defaults"))

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self.llm_defaults is not None:
            result["llm_defaults"] = self.llm_defaults
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
