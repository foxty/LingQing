"""Domain models for tenant module."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.shared.domain.base_domain_model import BaseDomainModel


@dataclass
class TenantConfig:
    """Typed tenant configuration (sub-model of TenantDomain).

    Stored as JSON in tenants.config field.
    LLM config and Embedding config are stored as encrypted dict - conversion to DTO happens in service layer.
    """

    llm_config: dict[str, Any] | None = None
    embedding_config: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "TenantConfig":
        """Parse configuration from config JSON.

        Args:
            data: Raw config dict from database (can be None)

        Returns:
            TenantConfig with parsed data
        """
        if not data:
            return cls()

        return cls(
            llm_config=data.get("llm_config"),
            embedding_config=data.get("embedding_config"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage.

        Returns:
            Dict ready for JSON serialization
        """
        result: dict[str, Any] = {}
        if self.llm_config is not None:
            result["llm_config"] = self.llm_config
        if self.embedding_config is not None:
            result["embedding_config"] = self.embedding_config
        return result


@dataclass
class TenantDomain(BaseDomainModel):
    """Tenant domain model for multi-tenancy."""

    id: int
    name: str
    slug: str | None
    description: str | None
    config: TenantConfig = field(default_factory=TenantConfig)  # Parsed typed configuration
    status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def is_active(self) -> bool:
        """Check if tenant is active."""
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
