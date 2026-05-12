"""SQLite database manager using SQLAlchemy.

This module provides SQLite implementation of the AnalyticsDBManager interface
using SQLAlchemy, suitable for development, testing, and single-tenant deployments.
Extends RelationalDBManager for uniform API and code reuse across all relational databases.
"""

from pathlib import Path

from apps.shared.domain.value_objects import DatabaseConnectionVO
from apps.shared.infra.analytics_db.relational_db_manager import RelationalDBManager
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class SQLiteManager(RelationalDBManager):
    """SQLite database manager using SQLAlchemy.

    Extends RelationalDBManager to provide SQLite-specific behavior.
    By default, SQLite is assumed to be managed (managed=True) since it's
    typically a tenant-owned workspace database.

    Uses SQLAlchemy for connection management and SQL execution, ensuring
    consistent behavior with other relational database managers.
    """

    def __init__(self, tenant_id: int, connection: DatabaseConnectionVO, managed: bool = True):
        """Initialize SQLite manager.

        Args:
            tenant_id: Tenant ID
            connection: Database connection configuration
            managed: If True, allow write/DDL operations (default True for SQLite)

        Raises:
            ValueError: If connection URL does not start with 'sqlite:///'
        """
        connection_url = connection.to_url("sqlite")
        if not connection_url.startswith("sqlite:///"):
            raise ValueError(f"Invalid SQLite URL: {connection_url}. Must start with 'sqlite:///'")

        # Ensure database directory exists before connecting
        db_path = Path(connection_url.replace("sqlite:///", ""))
        db_path.parent.mkdir(parents=True, exist_ok=True)

        super().__init__(tenant_id, connection, managed)
