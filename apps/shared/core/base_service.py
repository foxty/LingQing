"""Base service classes for business logic layer."""

from abc import ABC

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class TenantAwareService(ABC):
    """Base class for services that enforce tenant isolation.

    All operations are automatically scoped to the tenant context.
    Subclasses must implement business logic within tenant boundaries.

    Usage:
        class DocumentService(TenantAwareService):
            def __init__(self, db: AsyncSession, tenant_id: int):
                super().__init__(tenant_id)
                self.db = db

            async def list_documents(self):
                # Use self.tenant_id for all operations
                return await repo.filter_by_tenant(self.tenant_id)
    """

    def __init__(self, tenant_id: int, db_session: AsyncSession | None = None):
        """Initialize with tenant context.

        Args:
            tenant_id: Tenant ID to scope all operations

        Raises:
            ValueError: If tenant_id is invalid
        """
        self._validate_tenant_id(tenant_id)
        self.tenant_id = tenant_id
        self.db_session = db_session
        logger.debug(f"Initialized {self.__class__.__name__} for tenant {tenant_id}")

    def _validate_tenant_id(self, tenant_id: int) -> None:
        """Validate tenant_id is provided and valid.

        Args:
            tenant_id: Tenant ID to validate

        Raises:
            ValueError: If tenant_id is invalid
        """
        if not tenant_id or tenant_id <= 0:
            raise ValueError(f"Valid tenant_id is required for {self.__class__.__name__}")

    def _ensure_tenant_scope(self, entity_tenant_id: int) -> None:
        """Validate entity belongs to current tenant.

        Use this method to verify entities loaded from database belong
        to the current tenant context before performing operations.

        Args:
            entity_tenant_id: Tenant ID from entity

        Raises:
            PermissionError: If entity doesn't belong to current tenant
        """
        if entity_tenant_id != self.tenant_id:
            raise PermissionError(
                f"Access denied: entity belongs to tenant {entity_tenant_id}, "
                f"current context is tenant {self.tenant_id}"
            )

