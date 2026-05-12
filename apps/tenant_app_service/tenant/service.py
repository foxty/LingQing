"""Tenant service - unified entry point for tenant-related operations.

This service provides a centralized interface for accessing tenant
and stats information. Other applications should use this service
instead of directly accessing repositories.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.base_service import TenantAwareService
from apps.shared.data_source.repository import AssetMetadataRepository
from apps.shared.document import DBDocumentRepository
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_catalog.repository import AgentCatalogRepository
from apps.tenant_app_service.tenant.repository import TenantRepository
from apps.tenant_app_service.tenant.schemas import StatsResponse

logger = get_logger(__name__)


class SingleTenantService(TenantAwareService):
    """Unified service for tenant and stats operations.

    All public methods return DTOs (schemas), not domain models.
    """

    def __init__(
        self,
        tenant_id: int,
        tenant_repo: TenantRepository,
        agent_repo: AgentCatalogRepository,
        document_repo: DBDocumentRepository,
        asset_repo: AssetMetadataRepository,
    ):
        super().__init__(tenant_id)
        self.tenant_repo = tenant_repo
        self.agent_repo = agent_repo
        self.document_repo = document_repo
        self.asset_repo = asset_repo

    @classmethod
    def create(cls, db: AsyncSession, tenant_id: int) -> "SingleTenantService":
        tenant_repo = TenantRepository(db)
        agent_repo = AgentCatalogRepository(db)
        document_repo = DBDocumentRepository(db)
        asset_repo = AssetMetadataRepository(db)
        return cls(tenant_id, tenant_repo, agent_repo, document_repo, asset_repo)

    async def get_stats(self) -> StatsResponse:
        logger.info(f"Retrieving stats for tenant: {self.tenant_id}")

        total_documents, total_storage_bytes = await self.document_repo.get_document_stats(self.tenant_id)
        total_assets = await self.asset_repo.count_by_tenant(self.tenant_id)
        total_agents = await self.agent_repo.count_active(self.tenant_id)

        return StatsResponse(
            total_documents=total_documents,
            total_assets=total_assets,
            total_agents=total_agents,
            total_storage_bytes=total_storage_bytes,
        )
