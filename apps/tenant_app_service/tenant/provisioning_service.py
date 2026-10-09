"""Tenant provisioning service for managing tenant infrastructure.

Handles one-time setup and teardown operations for tenant environments,
including database and user provisioning/deprovisioning.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from apps.config import EnvConfig
from apps.shared.core.exceptions import InternalServiceError
from apps.shared.core.policy_seed import seed_default_policies
from apps.shared.core.tag_seed import seed_default_tags
from apps.shared.domain.value_objects import DatabaseConnectionVO
from apps.shared.tasks.system.reconciler import reconcile_for_tenant
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.auth.repository import UserRepository
from apps.tenant_app_service.tenant.provisioning_executor import ProvisioningExecutor
from apps.tenant_app_service.tenant.repository import TenantRepository

logger = get_logger(__name__)


class TenantProvisioningService:
    """Service for provisioning and managing tenant infrastructure.

    Separates business logic from database-specific details:
    - Orchestrates tenant creation and analytics DB provisioning
    - Delegates all infrastructure operations to ProvisioningExecutor
    - Database-agnostic: works with any executor implementation
    - Returns domain models (AnalyticsDBInfo) for storage

    Can be used by:
    - tenant_cli.py (CLI management)
    - Admin portal (future UI)
    - Other services (programmatic provisioning)

    Example:
        executor = PostgreSQLProvisioningExecutor(admin_url)
        service = TenantProvisioningService(db, executor)
        db_info = await service.provision_analytics_db(tenant_id)
    """

    def __init__(
        self,
        db: AsyncSession,
        provisioning_executor: ProvisioningExecutor,
    ):
        """Initialize provisioning service.

        Args:
            db: AsyncSession for main tenant database
            provisioning_executor: ProvisioningExecutor implementation
                (e.g., PostgreSQLProvisioningExecutor, MySQLProvisioningExecutor)
        """
        self.db = db
        self.executor = provisioning_executor
        self.tenant_repo = TenantRepository(db)
        self.user_repo = UserRepository(db)
        self.db_prefix = EnvConfig.TENANT_DB_PREFIX
        self.db_suffix = EnvConfig.TENANT_DB_SUFFIX

    async def get_tenant_by_slug(self, slug: str) -> dict | None:
        """Get tenant information by slug.

        Args:
            slug: Tenant URL identifier

        Returns:
            Dict with tenant info or None if not found
        """
        tenant = await self.tenant_repo.get_by_slug(slug)
        if not tenant:
            return None
        return {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "description": tenant.description,
            "status": tenant.status,
        }

    async def get_all_tenants(self) -> list[dict]:
        """Get all tenants.

        Returns:
            List of dicts with tenant info
        """
        tenants = await self.tenant_repo.get_all()
        return [
            {
                "id": t.id,
                "name": t.name,
                "slug": t.slug,
                "description": t.description,
                "status": t.status,
            }
            for t in tenants
        ]

    async def get_tenant_with_user_count(self, slug: str) -> dict | None:
        """Get tenant information with user count by slug.

        Args:
            slug: Tenant URL identifier

        Returns:
            Dict with tenant info and user_count, or None if not found
        """
        tenant = await self.tenant_repo.get_by_slug(slug)
        if not tenant:
            return None

        users = await self.user_repo.get_by_tenant(tenant.id)
        return {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "description": tenant.description,
            "status": tenant.status,
            "user_count": len(users),
        }

    def _get_tenant_db_name(self, tenant_id: int) -> str:
        """Get database name for tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Database name (e.g., 'tenant_1_analytics')
        """
        return f"{self.db_prefix}{tenant_id}{self.db_suffix}"

    def _get_tenant_role_name(self, tenant_id: int) -> str:
        """Get role/user name for tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Role name (e.g., 'tenant_1_user')
        """
        return f"{self.db_prefix}{tenant_id}_user"

    async def provision_tenant(
        self,
        name: str,
        slug: str | None = None,
        description: str | None = None,
        config: dict | None = None,
    ) -> dict:
        """Create a new tenant in the main database.

        This creates the tenant record but does NOT provision analytics DB.
        Use provision_analytics_db separately if needed.

        Args:
            name: Tenant display name
            slug: Tenant URL identifier
            description: Tenant description
            config: Tenant configuration

        Returns:
            Dict with tenant_id and tenant info
        """
        logger.info(f"Provisioning tenant: {name} ({slug})")
        tenant = await self.tenant_repo.create_tenant(
            name=name,
            slug=slug,
            description=description,
            config=config,
        )
        await seed_default_tags(self.db, tenant.id)
        await seed_default_policies(self.db, tenant.id)
        task_count = await reconcile_for_tenant(tenant.id, session=self.db)
        logger.info(
            "Successfully provisioned tenant %s with %s system scheduled tasks",
            tenant.id,
            task_count,
        )
        return {"id": tenant.id, "name": tenant.name, "slug": tenant.slug}

    async def unprovision_tenant_user(self, tenant_id: int, user_id: int) -> None:
        """Delete a user from a tenant.

        Args:
            tenant_id: Tenant ID
            user_id: User ID to delete
        """
        logger.info(f"Deleting user {user_id} from tenant {tenant_id}")
        await self.user_repo.delete(user_id)
        logger.info(f"Successfully deleted user {user_id}")

    async def provision_analytics_db(
        self,
        tenant_id: int,
        pg_host: str | None = None,
        pg_port: int | None = None,
    ) -> DatabaseConnectionVO:
        """Create and initialize analytics database for tenant.

        Creates:
        1. PostgreSQL role: tenant_{id}_user
        2. PostgreSQL database: tenant_{id}_analytics
        3. Grants privileges
        4. Initializes schema

        Args:
            tenant_id: Tenant ID
            pg_host: PostgreSQL host (defaults to EnvConfig.TENANT_APP_DB_HOST)
            pg_port: PostgreSQL port (defaults to EnvConfig.TENANT_APP_DB_PORT)

        Returns:
            DatabaseConnectionVO with connection details (for storage in DataSource)
        """
        pg_host = pg_host or EnvConfig.TENANT_APP_DB_HOST
        pg_port = pg_port or EnvConfig.TENANT_APP_DB_PORT
        db_name = self._get_tenant_db_name(tenant_id)
        role_name = self._get_tenant_role_name(tenant_id)

        logger.info(f"Provisioning analytics DB for tenant {tenant_id}: {db_name}")

        try:
            info = await self.executor.provision_database(
                db_name=db_name,
                role_name=role_name,
                host=pg_host,
                port=pg_port,
            )
            logger.info(f"Successfully provisioned analytics DB for tenant {tenant_id}")
            return info

        except Exception as e:
            raise InternalServiceError(f"Analytics DB provisioning failed for tenant {tenant_id}: {str(e)}") from e

    async def unprovision_analytics_db(
        self,
        tenant_id: int,
        pg_host: str | None = None,
        pg_port: int | None = None,
    ) -> None:
        """Drop analytics database and role for tenant.

        Args:
            tenant_id: Tenant ID
            pg_host: PostgreSQL host (defaults to EnvConfig.TENANT_APP_DB_HOST)
            pg_port: PostgreSQL port (defaults to EnvConfig.TENANT_APP_DB_PORT)
        """
        db_name = self._get_tenant_db_name(tenant_id)
        role_name = self._get_tenant_role_name(tenant_id)

        logger.info(f"Deprovisioning analytics DB for tenant {tenant_id}: {db_name}")

        try:
            # Step 1: Drop database (terminates connections)
            await self.executor.drop_database(db_name)

            # Step 2: Drop role
            await self.executor.drop_role(role_name)

            logger.info(f"Successfully deprovisioned analytics DB for tenant {tenant_id}")

        except Exception as e:
            raise InternalServiceError(f"Analytics DB deprovisioning failed for tenant {tenant_id}: {str(e)}") from e
