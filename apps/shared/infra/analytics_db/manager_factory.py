"""Factory functions for creating database managers.

Provides unified interface for creating DB managers across different data source types
using a registry pattern for easy extensibility.
"""

from apps.shared.data_source.domain import DataSourceDomain
from apps.shared.domain.value_objects import DatabaseConnectionVO, DataSourceType
from apps.shared.infra.analytics_db.base_manager import AnalyticsDBManager
from apps.shared.infra.analytics_db.databricks_manager import DatabricksManager
from apps.shared.infra.analytics_db.errors import InvalidConfigurationError
from apps.shared.infra.analytics_db.postgres_manager import PostgresManager
from apps.shared.infra.analytics_db.relational_db_manager import RelationalDBManager
from apps.shared.infra.analytics_db.sqlite_manager import SQLiteManager
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

# Registry of available database managers
_DB_MANAGER_REGISTRY: dict[str, type[AnalyticsDBManager]] = {}


def register_db_manager(db_type: str, manager_class: type[AnalyticsDBManager]) -> None:
    """Register a database manager class for a specific database type.

    Args:
        db_type: Database type identifier (e.g., 'postgres', 'mysql', 'sqlite')
        manager_class: AnalyticsDBManager subclass to register
    """
    _DB_MANAGER_REGISTRY[db_type] = manager_class
    logger.debug(f"Registered DB manager for type '{db_type}': {manager_class.__name__}")


# Register default managers
register_db_manager(DataSourceType.SQLITE, SQLiteManager)
register_db_manager(DataSourceType.POSTGRES, PostgresManager)
register_db_manager(DataSourceType.MYSQL, RelationalDBManager)
register_db_manager(DataSourceType.DATABRICKS, DatabricksManager)


def get_db_manager_for_datasource(data_source: DataSourceDomain) -> AnalyticsDBManager:
    """Get appropriate database manager for a data source.

    Factory function that returns the correct DB manager implementation
    based on data source type and configuration. Looks up the manager class
    in the registry and instantiates it with appropriate settings.

    Args:
        data_source: Data source domain object

    Returns:
        AnalyticsDBManager subclass instance

    Raises:
        ValueError: If data source config is invalid or type is unsupported

    Example:
        async with get_db_manager_for_datasource(data_source) as db:
            df = await db.query("SELECT * FROM table")
    """
    manager_class = _DB_MANAGER_REGISTRY.get(data_source.type)
    if manager_class:
        managed = data_source.is_managed
        return manager_class(tenant_id=data_source.tenant_id, connection=data_source.connection, managed=managed)

    raise ValueError(f"Unsupported data source type: {data_source.type}")


def create_db_manager_from_config(
    tenant_id: int,
    db_type: str,
    config: dict,
    managed: bool | None = None,
) -> AnalyticsDBManager:
    """Create database manager from raw configuration.

    Used for testing connections and discovering assets before data source creation.

    Args:
        tenant_id: Tenant ID
        db_type: Database type string (postgres or mysql)
        config: Connection configuration
        managed: If True, allow write operations. If None, use default for type.

    Returns:
        AnalyticsDBManager instance

    Raises:
        InvalidConfigurationError: If configuration is invalid

    Example:
        manager = create_db_manager_from_config(
            tenant_id=1,
            db_type="postgres",
            config={"host": "localhost", "database": "mydb", ...},
            managed=False
        )
        async with manager:
            assets, _ = await manager.discover_assets()
    """
    if db_type in [DataSourceType.POSTGRES, DataSourceType.MYSQL, DataSourceType.DATABRICKS]:
        connection = DatabaseConnectionVO.from_dict(config)
        managed_flag = managed if managed is not None else False

        manager_class = _DB_MANAGER_REGISTRY.get(db_type, RelationalDBManager)
        return manager_class(tenant_id=tenant_id, connection=connection, managed=managed_flag)

    else:
        raise InvalidConfigurationError(f"Unsupported database type: {db_type}")
