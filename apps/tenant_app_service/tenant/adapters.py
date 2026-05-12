"""Adapters for Tenant domain model conversions."""

from apps.shared.db import models as db_models
from apps.shared.schemas.model_config import TenantLLMConfigDTO
from apps.shared.schemas.tenant import TenantDTO
from apps.tenant_app_service.tenant.domain import TenantConfig, TenantDomain


def db_tenant_to_domain(db_tenant: db_models.Tenant) -> TenantDomain:
    """Convert DB Tenant to Domain Tenant.

    Parses config JSON into typed TenantConfig.
    """
    config = TenantConfig.from_dict(db_tenant.config)

    return TenantDomain(
        id=db_tenant.id,
        name=db_tenant.name,
        slug=db_tenant.slug,
        description=db_tenant.description,
        config=config,
        status=db_tenant.status,
        created_at=db_tenant.created_at,
        updated_at=db_tenant.updated_at,
    )


def domain_tenant_to_llm_config_dto(domain_tenant: TenantDomain) -> TenantLLMConfigDTO | None:
    """Convert TenantDomain to TenantLLMConfigDTO for API requests."""
    if not domain_tenant.config.llm_config:
        return None
    return TenantLLMConfigDTO(**domain_tenant.config.llm_config)


def domain_tenant_to_db_dict(domain_tenant: TenantDomain) -> dict:
    """Convert Domain Tenant to dict for DB operations.

    Excludes id and timestamps (managed by DB).
    Serializes config back to JSON.
    """
    return {
        "name": domain_tenant.name,
        "slug": domain_tenant.slug,
        "description": domain_tenant.description,
        "config": domain_tenant.config.to_dict(),
        "status": domain_tenant.status,
    }


def domain_tenant_to_dto(domain_tenant: TenantDomain) -> TenantDTO:
    """Convert Domain Tenant to TenantDTO."""
    config = None
    if domain_tenant.config.llm_config:
        config = TenantLLMConfigDTO(**domain_tenant.config.llm_config)
    return TenantDTO(
        id=domain_tenant.id,
        name=domain_tenant.name,
        description=domain_tenant.description or "",
        slug=domain_tenant.slug,
        config=config,
    )
