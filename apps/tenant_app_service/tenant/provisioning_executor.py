"""Abstract provisioning executor interface.

Defines the contract for database-agnostic tenant infrastructure provisioning.
Allows different database implementations (PostgreSQL, MySQL, etc.) to provide
their own provisioning logic while keeping the service layer database-agnostic.
"""

from abc import ABC, abstractmethod

from apps.shared.domain.value_objects import DatabaseConnectionVO


class ProvisioningExecutor(ABC):
    """Abstract executor for provisioning tenant database infrastructure.

    Implementations handle database-specific operations like creating databases,
    roles, granting privileges, and initializing schemas.

    All operations must be async-compatible.
    """

    @abstractmethod
    async def provision_database(self, db_name: str, role_name: str, host: str, port: int) -> DatabaseConnectionVO:
        """Provision a tenant analytics database and return connection info.

        Implementations should:
        1. Create login role with password
        2. Create database owned by the role
        3. Grant required privileges for CRUD in public schema
        4. Initialize schema based on provided metadata

        Returns: DatabaseConnectionVO for DataSource storage
        """
        pass

    @abstractmethod
    async def drop_database(self, db_name: str) -> None:
        pass

    @abstractmethod
    async def drop_role(self, role_name: str) -> None:
        pass
