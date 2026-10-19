"""Shared DB wiring for chat application services."""

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.repository import ArtifactRepository
from apps.shared.core.base_service import TenantAwareService
from apps.shared.core.exceptions import AuthorizationError
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agent_pool import get_agent_pool
from apps.tenant_app_service.chat.message_repository import MessageRepository
from apps.tenant_app_service.chat.repository import ThreadRepository
from apps.tenant_app_service.tenant.adapters import db_tenant_to_domain
from apps.tenant_app_service.tenant.domain import TenantDomain
from apps.tenant_app_service.tenant.repository import TenantRepository

MAX_THREADS_PER_USER = 20
DEFAULT_HISTORY_MESSAGE_LIMIT = 1
HITL_CONTINUATION_HISTORY_LIMIT = 12


class ChatServiceBase(TenantAwareService):
    """Tenant-scoped repos shared by thread and turn services."""

    def __init__(self, tenant_id: int, db: AsyncSession):
        super().__init__(tenant_id=tenant_id, db_session=db)
        self.db = db
        self.logger = get_logger(self.__class__.__name__)
        self.agent_pool = get_agent_pool()
        self.thread_repo = ThreadRepository(db)
        self.message_repo = MessageRepository(db)
        self.tenant_repo = TenantRepository(db)
        self.artifact_repo = ArtifactRepository(db)

    async def get_tenant_domain(self) -> TenantDomain:
        tenant = await self.tenant_repo.get_by_id(self.tenant_id)
        if not tenant:
            raise AuthorizationError(f"Tenant {self.tenant_id} not found")
        return db_tenant_to_domain(tenant)
