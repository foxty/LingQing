"""Relational database manager for SQL-based databases via SQLAlchemy.

Supports PostgreSQL, MySQL, MariaDB, SQLite, and other SQLAlchemy-compatible databases.
Subclasses can override bulk_load() and other methods for database-specific optimizations.
"""

from typing import Any

import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    inspect,
    text,
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from apps.config import EnvConfig
from apps.shared.data_source.domain import AssetMetadataDomain
from apps.shared.data_source.schemas import DiscoveredAsset, DiscoveredColumn
from apps.shared.domain.value_objects import AssetType, DatabaseConnectionVO, DataType
from apps.shared.infra.analytics_db.base_manager import AnalyticsDBManager
from apps.shared.infra.analytics_db.errors import (
    ConnectionError,
    QueryExecutionError,
    TableNotFoundError,
)
from apps.shared.utils.logger import get_logger
from apps.shared.utils.sql_utils import validate_sql_identifier


class RelationalDBManager(AnalyticsDBManager):
    """Manager for relational database connections via SQLAlchemy.

    Supports PostgreSQL, MySQL, MariaDB, SQLite, Oracle, and other
    SQLAlchemy-compatible databases. Provides read, write, and metadata
    operations with optional write permission control via the `managed` flag.
    """

    def __init__(self, tenant_id: int, connection: DatabaseConnectionVO, managed: bool = False):
        """Initialize relational DB manager.

        Args:
            tenant_id: Tenant ID
            connection: Database connection configuration
            managed: If True, allow write/DDL operations. If False, read-only.
        """
        super().__init__(tenant_id, connection, managed)
        self.logger = get_logger(__name__, f"tenant:{tenant_id}")
        self._engine: AsyncEngine | None = None
        self._session_maker: async_sessionmaker | None = None

    def _get_engine(self) -> AsyncEngine:
        """Get or create async SQLAlchemy engine."""
        if self._engine is None:
            connection_url = self.connection.to_url("postgresql")

            self._engine = create_async_engine(
                connection_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
            self._session_maker = async_sessionmaker(self._engine, expire_on_commit=False)
        return self._engine

    # ========== Abstract Method Implementations ==========

    async def _connect(self) -> None:
        """Establish database connection (implementation-specific)."""
        try:
            self._get_engine()
            self.logger.debug(f"Relational DB engine created for tenant {self.tenant_id}")
        except SQLAlchemyError as e:
            self.logger.error(f"Failed to create database engine: {e}")
            raise ConnectionError(f"Failed to connect to database: {str(e)}")

    async def _disconnect(self) -> None:
        """Close database connection (implementation-specific)."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None
            self.logger.debug(f"Relational DB engine disposed for tenant {self.tenant_id}")

    async def create_table(self, asset: AssetMetadataDomain) -> None:
        """Create table from asset metadata.

        Args:
            asset: Asset metadata containing table schema

        Raises:
            PermissionError: If database is unmanaged
            QueryExecutionError: If table creation fails
        """
        self._check_write_permission("create_table")

        if not asset or not asset.columns:
            raise ValueError("Asset metadata must contain at least one column")

        try:
            engine = self._get_engine()
            metadata = MetaData()

            # Map asset columns to SQLAlchemy Column objects
            columns = []
            for col in asset.columns:
                sa_col = Column(
                    col.name,
                    self._get_sqlalchemy_type(col.data_type),
                )
                columns.append(sa_col)

            # Create the table
            Table(asset.asset_name, metadata, *columns)
            async with engine.begin() as conn:
                await conn.run_sync(metadata.create_all)

            self.logger.info(f"Created table '{asset.asset_name}' with {len(columns)} columns")
        except SQLAlchemyError as e:
            self.logger.error(f"Failed to create table: {e}")
            raise QueryExecutionError(f"Failed to create table '{asset.asset_name}': {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error during table creation: {e}")
            raise QueryExecutionError(f"Failed to create table '{asset.asset_name}': {str(e)}")

    @staticmethod
    def _get_sqlalchemy_type(data_type: DataType):
        """Map DataType enum to SQLAlchemy column type.

        Args:
            data_type: DataType enum value

        Returns:
            Appropriate SQLAlchemy column type
        """
        type_map = {
            DataType.INTEGER: Integer,
            DataType.FLOAT: Float,
            DataType.TEXT: String,
            DataType.BOOLEAN: Boolean,
            DataType.DATE: Date,
            DataType.DATETIME: DateTime,
            DataType.JSON: String,  # JSON stored as TEXT
        }
        return type_map.get(data_type, String)

    async def drop_table(self, table_name: str) -> None:
        """Drop table.

        Args:
            table_name: Name of the table to drop

        Raises:
            PermissionError: If database is unmanaged
        """
        self._check_write_permission("drop_table")
        safe_name = validate_sql_identifier(table_name, field_name="table_name")
        try:
            engine = self._get_engine()
            async with engine.begin() as conn:
                await conn.execute(text(f"DROP TABLE IF EXISTS {safe_name}"))
            self.logger.info(f"Dropped table '{table_name}'")
        except SQLAlchemyError as e:
            self.logger.error(f"Failed to drop table: {e}")
            raise QueryExecutionError(f"Failed to drop table '{table_name}': {str(e)}")

    async def table_exists(self, table_name: str) -> bool:
        """Check if table exists.

        Args:
            table_name: Name of the table

        Returns:
            True if table exists, False otherwise
        """
        try:
            engine = self._get_engine()
            async with engine.connect() as conn:
                result = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
                return table_name in result
        except Exception as e:
            self.logger.error(f"Failed to check table existence: {e}")
            return False

    async def list_tables(self) -> list[str]:
        """List all tables in the database.

        Returns:
            List of table names
        """
        try:
            engine = self._get_engine()
            async with engine.connect() as conn:
                return await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
        except Exception as e:
            self.logger.error(f"Failed to list tables: {e}")
            return []

    async def insert_dataframe(self, table_name: str, df: pd.DataFrame, if_exists: str = "append") -> int:
        """Insert data from a pandas DataFrame.

        Args:
            table_name: Name of the table to insert into
            df: DataFrame containing the data
            if_exists: What to do if table exists: 'fail', 'replace', or 'append'

        Returns:
            Number of rows inserted

        Raises:
            PermissionError: If database is unmanaged
            ValueError: If table does not exist or DataFrame schema mismatches
            QueryExecutionError: If insertion fails
        """
        self._check_write_permission("insert_dataframe")

        try:
            engine = self._get_engine()

            def _insert_sync(sync_conn):
                df.to_sql(table_name, sync_conn, if_exists=if_exists, index=False)

            async with engine.begin() as conn:
                await conn.run_sync(_insert_sync)

            self.logger.info(f"Inserted {len(df)} rows into table '{table_name}'")
            return len(df)
        except SQLAlchemyError as e:
            self.logger.error(f"Failed to insert dataframe: {e}")
            raise QueryExecutionError(f"Failed to insert into '{table_name}': {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error during insert: {e}")
            raise ValueError(f"Invalid DataFrame or schema: {str(e)}")

    async def query(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        """Execute a SQL query and return results as DataFrame.

        Args:
            sql: SQL query string
            params: Optional query parameters for parameterized queries

        Returns:
            Query results as DataFrame
        """
        engine = self._get_engine()

        async with engine.connect() as conn:
            stmt = text(sql)

            if params:
                result = await conn.execute(stmt, params)
            else:
                result = await conn.execute(stmt)

            # Fetch all rows and convert to DataFrame
            rows = result.all()
            if rows:
                df = pd.DataFrame(rows, columns=result.keys())
            else:
                df = pd.DataFrame(columns=result.keys())

        return df

    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute a SQL statement (INSERT, UPDATE, DELETE).

        Args:
            sql: SQL statement string
            params: Optional statement parameters

        Returns:
            Number of rows affected

        Raises:
            PermissionError: If database is unmanaged
            QueryExecutionError: If execution fails
        """
        self._check_write_permission("execute")

        try:
            engine = self._get_engine()
            async with engine.begin() as conn:
                result = await conn.execute(text(sql), params or {})
                return result.rowcount or 0
        except SQLAlchemyError as e:
            self.logger.error(f"Execute failed: {e}")
            raise QueryExecutionError(f"Execute failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error during execute: {e}")
            raise QueryExecutionError(f"Invalid statement: {str(e)}")

    async def execute_transaction(self, statements: list[tuple[str, dict[str, Any] | None]]) -> None:
        """Execute multiple statements in one database transaction."""
        self._check_write_permission("execute_transaction")

        try:
            engine = self._get_engine()
            async with engine.begin() as conn:
                for sql, params in statements:
                    await conn.execute(text(sql), params or {})
        except SQLAlchemyError as e:
            self.logger.error(f"Transactional execute failed: {e}")
            raise QueryExecutionError(f"Transactional execute failed: {str(e)}")
        except Exception as e:
            self.logger.error(f"Unexpected error during transactional execute: {e}")
            raise QueryExecutionError(f"Invalid transactional statement: {str(e)}")

    async def get_row_count(self, table_name: str) -> int:
        """Get the number of rows in a table.

        Args:
            table_name: Name of the table

        Returns:
            Number of rows

        Raises:
            TableNotFoundError: If table does not exist
            QueryExecutionError: If query fails
        """
        if not await self.table_exists(table_name):
            raise TableNotFoundError(f"Table '{table_name}' does not exist")

        try:
            engine = self._get_engine()
            async with engine.connect() as conn:
                result = await conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                return result.scalar() or 0
        except Exception as e:
            self.logger.error(f"Failed to get row count: {e}")
            raise QueryExecutionError(f"Failed to get row count for '{table_name}': {str(e)}")

    # ========== Optional Async Methods ==========

    async def test_connection(self) -> tuple[bool, str]:
        """Test database connection.

        Returns:
            Tuple of (success, message)
        """
        try:
            engine = self._get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True, "Connection successful"
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False, f"Connection failed: {str(e)}"

    async def discover_assets(
        self,
        query: str | None = None,
        include_schema: bool = True,
    ) -> tuple[list[DiscoveredAsset], int]:
        """Discover available tables and views.

        Args:
            query: Optional search query
            include_schema: Whether to include schema metadata

        Returns:
            Tuple of (assets, total)
        """
        try:
            engine = self._get_engine()

            async with engine.connect() as conn:

                def _get_names(sync_conn):
                    inspector = inspect(sync_conn)
                    return inspector.get_table_names(), inspector.get_view_names()

                table_names, view_names = await conn.run_sync(_get_names)

            asset_names = [(table_name, AssetType.TABLE) for table_name in table_names] + [
                (view_name, AssetType.VIEW) for view_name in view_names
            ]

            assets: list[DiscoveredAsset] = []
            for asset_name, asset_type in asset_names:
                if include_schema:
                    asset = await self._build_discovered_asset(asset_name, asset_type)
                    if asset:
                        assets.append(asset)
                else:
                    assets.append(
                        DiscoveredAsset(
                            name=asset_name,
                            type=asset_type,
                            row_count=None,
                            columns=None,
                            description=None,
                        )
                    )

            filtered_assets = assets
            if query:
                query_lower = query.lower()
                filtered_assets = [
                    asset
                    for asset in assets
                    if query_lower in asset.name.lower()
                    or (asset.description and query_lower in asset.description.lower())
                ]

            total = len(filtered_assets)
            capped_assets = filtered_assets[: EnvConfig.DISCOVERY_ASSET_LIMIT]

            return capped_assets, total
        except Exception as e:
            self.logger.error(f"Asset discovery failed: {e}")
            raise ValueError(f"Failed to discover assets: {str(e)}")

    async def discover_asset(self, asset_name: str, *, include_row_count: bool = True) -> DiscoveredAsset | None:
        """Discover a specific asset by name.

        Args:
            asset_name: Name of the asset to discover
            include_row_count: Whether to query row counts (can be slow on large tables)

        Returns:
            Discovered asset with metadata

        Raises:
            ValueError: If asset does not exist or discovery fails
        """
        try:
            engine = self._get_engine()

            async with engine.connect() as conn:

                def _get_asset_type(sync_conn):
                    inspector = inspect(sync_conn)
                    if asset_name in inspector.get_table_names():
                        return AssetType.TABLE
                    elif asset_name in inspector.get_view_names():
                        return AssetType.VIEW
                    return None

                asset_type = await conn.run_sync(_get_asset_type)

            if asset_type is None:
                return None

            asset = await self._build_discovered_asset(asset_name, asset_type, include_row_count=include_row_count)
            if asset is None:
                self.logger.warning(f"Failed to discover asset '{asset_name}'")
            return asset
        except Exception as e:
            self.logger.error(f"Asset discovery failed for '{asset_name}': {e}")
            raise ValueError(f"Failed to discover asset '{asset_name}': {self._format_exception_message(e)}")

    @staticmethod
    def _format_exception_message(exc: Exception) -> str:
        message = str(exc).strip()
        if message:
            return message
        return f"{type(exc).__name__} (no details)"

    async def _build_discovered_asset(
        self,
        asset_name: str,
        asset_type: AssetType,
        *,
        include_row_count: bool = True,
    ) -> DiscoveredAsset | None:
        """Build discovered asset metadata for a single table or view.

        Args:
            asset_name: Name of the asset
            asset_type: Type of asset (TABLE or VIEW)

        Returns:
            DiscoveredAsset with metadata, or None if metadata retrieval fails
        """
        try:
            engine = self._get_engine()

            async with engine.connect() as conn:

                def _get_metadata(sync_conn):
                    inspector = inspect(sync_conn)
                    columns = inspector.get_columns(asset_name)
                    comment = inspector.get_table_comment(asset_name).get("text", "") or ""
                    row_count = None

                    # Get row count for tables only
                    if include_row_count and asset_type == AssetType.TABLE:
                        try:
                            result = sync_conn.execute(text(f"SELECT COUNT(*) FROM {asset_name}"))
                            row_count = result.scalar()
                        except Exception as e:
                            self.logger.warning(f"Failed to get row count for {asset_name}: {e}")

                    return comment, columns, row_count

                comment, columns, row_count = await conn.run_sync(_get_metadata)

            return DiscoveredAsset(
                name=asset_name,
                type=asset_type,
                row_count=row_count,
                description=comment,
                columns=[
                    DiscoveredColumn(
                        name=col["name"],
                        data_type=str(col["type"]),
                        comment=col.get("comment"),
                    )
                    for col in columns
                ],
            )
        except Exception as e:
            self.logger.warning(f"Failed to get metadata for {asset_type.value} {asset_name}: {e}")
            return DiscoveredAsset(
                name=asset_name,
                type=asset_type,
                row_count=None,
                columns=None,
            )

    async def close(self):
        """Close database connection."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None
