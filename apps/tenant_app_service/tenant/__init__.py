"""Tenant module.

External modules should only import the service layer and public DTOs.
Internal implementation details are hidden.
"""

from apps.shared.schemas.tenant import TenantDTO
from apps.tenant_app_service.tenant.domain import (
    TenantConfig,
    TenantDomain,
    TenantProvisioningError,
)
from apps.tenant_app_service.tenant.postgres_executor import PostgreSQLProvisioningExecutor
from apps.tenant_app_service.tenant.provisioning_executor import ProvisioningExecutor
from apps.tenant_app_service.tenant.provisioning_service import TenantProvisioningService
from apps.tenant_app_service.tenant.repository import TenantRepository
from apps.tenant_app_service.tenant.schemas import (
    ModelInfoDTO,
    ModelProviderGroupDTO,
    StatsResponse,
    TenantUsageSummaryResponse,
    TokenUsageEventsResponse,
)
from apps.tenant_app_service.tenant.service import SingleTenantService
from apps.tenant_app_service.tenant.user_management_service import TenantUserManagementService

__all__ = [
    "TenantDomain",
    "TenantConfig",
    "TenantDTO",
    "ModelInfoDTO",
    "ModelProviderGroupDTO",
    "TenantRepository",
    "SingleTenantService",
    "TenantUserManagementService",
    "StatsResponse",
    "TenantUsageSummaryResponse",
    "TokenUsageEventsResponse",
    "TenantProvisioningService",
    "ProvisioningExecutor",
    "PostgreSQLProvisioningExecutor",
    "TenantProvisioningError",
]
