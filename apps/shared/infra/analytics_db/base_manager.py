"""Abstract base class for analytics database managers.

This module defines the interface that all analytics database implementations
must follow, ensuring consistent behavior across different database backends
(SQLite, DuckDB, PostgreSQL, etc.).
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import pandas as pd

from apps.shared.data_source.domain import AssetMetadataDomain
from apps.shared.data_source.schemas import DiscoveredAsset
from apps.shared.domain.value_objects import DatabaseConnectionVO
from apps.shared.infra.analytics_db.errors import PermissionError
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class AnalyticsDBManager(ABC):
    def __init__(self, tenant_id: int, connection: DatabaseConnectionVO, managed: bool = False):
        self.tenant_id = tenant_id
        self.connection = connection
        self.managed = managed
        self._is_connected = False

    @abstractmethod
    async def _connect(self) -> None:
        """Establish database connection (implementation-specific).

        Subclasses must implement this method to create the actual connection.
        This is called by connect() which manages connection state.
        """
        pass

    @abstractmethod
    async def _disconnect(self) -> None:
        """Close database connection (implementation-specific).

        Subclasses must implement this method to close the actual connection.
        This is called by disconnect() which manages connection state.
        """
        pass

    async def connect(self) -> None:
        """Establish database connection.

        This method is idempotent - calling it multiple times is safe.
        Use as context manager (with statement) for automatic resource management.
        """
        if not self._is_connected:
            logger.debug(f"Connecting to database for tenant {self.tenant_id}")
            await self._connect()
            self._is_connected = True
            logger.debug("Database connection established")

    async def disconnect(self) -> None:
        """Close database connection.

        This method is idempotent - calling it multiple times is safe.
        """
        if self._is_connected:
            logger.debug(f"Disconnecting from database for tenant {self.tenant_id}")
            await self._disconnect()
            self._is_connected = False
            logger.debug("Database connection closed")

    @property
    def is_connected(self) -> bool:
        """Check if database is currently connected.

        Returns:
            True if connected, False otherwise
        """
        return self._is_connected

    def _check_write_permission(self, operation: str) -> None:
        """Enforce write permission based on managed flag.

        Args:
            operation: Name of the write operation (e.g., 'insert', 'update', 'create_table')

        Raises:
            PermissionError: If database is unmanaged (managed=False)
        """
        if not self.managed:
            raise PermissionError(
                f"Cannot perform '{operation}' on unmanaged database. Set managed=True to allow write operations."
            )

    @abstractmethod
    async def create_table(self, asset: AssetMetadataDomain) -> None:
        pass

    @abstractmethod
    async def drop_table(self, table_name: str) -> None:
        pass

    @abstractmethod
    async def table_exists(self, table_name: str) -> bool:
        pass

    @abstractmethod
    async def list_tables(self) -> list[str]:
        """List all tables in the database.

        Returns:
            List of table names
        """
        pass

    @abstractmethod
    async def insert_dataframe(self, table_name: str, df: pd.DataFrame, if_exists: str = "append") -> int:
        """Insert data from a pandas DataFrame.

        Args:
            table_name: Name of the table to insert into
            df: DataFrame containing the data
            if_exists: What to do if table exists: 'fail', 'replace', or 'append'

        Returns:
            Number of rows inserted

        Raises:
            ValueError: If table does not exist or DataFrame schema mismatches
            RuntimeError: If insertion fails
        """
        pass

    @abstractmethod
    async def query(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        """Execute a SQL query and return results as DataFrame.

        Args:
            sql: SQL query string
            params: Optional query parameters for parameterized queries

        Returns:
            Query results as DataFrame

        Raises:
            ValueError: If query is invalid
            RuntimeError: If query execution fails
        """
        pass

    @abstractmethod
    async def execute(self, sql: str, params: dict[str, Any] | None = None) -> int:
        """Execute a SQL statement (INSERT, UPDATE, DELETE).

        Args:
            sql: SQL statement string
            params: Optional statement parameters

        Returns:
            Number of rows affected

        Raises:
            ValueError: If statement is invalid
            RuntimeError: If execution fails
        """
        pass

    async def execute_transaction(self, statements: list[tuple[str, dict[str, Any] | None]]) -> None:
        """Execute multiple SQL statements as one logical transaction.

        Default behavior falls back to sequential execute() calls for managers
        that do not provide native transaction support.
        """
        self._check_write_permission("execute_transaction")
        for sql, params in statements:
            await self.execute(sql, params=params)

    @abstractmethod
    async def get_row_count(self, table_name: str) -> int:
        """Get the number of rows in a table.

        Args:
            table_name: Name of the table

        Returns:
            Number of rows

        Raises:
            ValueError: If table does not exist
        """
        pass

    @abstractmethod
    async def discover_assets(
        self,
        query: str | None = None,
        include_schema: bool = True,
    ) -> tuple[list[DiscoveredAsset], int]:
        """Discover available tables and views in the database.

        Args:
            query: Optional search query
            include_schema: Whether to include schema metadata

        Returns:
            Tuple of (assets, total)

        Raises:
            RuntimeError: If asset discovery fails
        """
        pass

    @abstractmethod
    async def discover_asset(self, asset_name: str, *, include_row_count: bool = True) -> DiscoveredAsset:
        """Discover a specific asset by name.

        Args:
            asset_name: Name of the asset to discover
            include_row_count: Whether to query row counts (can be slow on large tables)

        Returns:
            Discovered asset with metadata

        Raises:
            ValueError: If asset does not exist
            RuntimeError: If discovery fails
        """
        pass

    async def import_csv(
        self,
        table_name: str,
        csv_path: Path,
        asset: AssetMetadataDomain | None = None,
        if_exists: str = "append",
    ) -> int:
        logger.info(f"Importing CSV from {csv_path} into table '{table_name}' for tenant {self.tenant_id}")

        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        df = pd.read_csv(csv_path)
        logger.info(f"Read {len(df)} rows from CSV")

        if asset and not await self.table_exists(table_name):
            await self.create_table(asset)

        rows_inserted = await self.insert_dataframe(table_name, df, if_exists=if_exists)
        logger.info(f"Imported {rows_inserted} rows into table '{table_name}'")

        return rows_inserted

    async def bulk_load(
        self,
        table_name: str,
        file_path: Path,
        file_format: str = "csv",
        asset: AssetMetadataDomain | None = None,
    ) -> int:
        """Load file directly into table without transferring through DataFrame.

        This is optimized for large files and uses database-specific bulk loading
        mechanisms (e.g., COPY for Postgres, LOAD DATA for MySQL). Default fallback
        to CSV reading + insert_dataframe if not overridden.

        Args:
            table_name: Name of the target table
            file_path: Path to the file to load
            file_format: File format ('csv', 'parquet', 'json', etc.)
            asset: Asset metadata for table creation if needed

        Returns:
            Number of rows loaded

        Raises:
            PermissionError: If database is unmanaged
            FileNotFoundError: If file does not exist
            NotImplementedError: If file format not supported
        """
        self._check_write_permission("bulk_load")

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if asset and not await self.table_exists(table_name):
            await self.create_table(asset)

        # Default fallback: read CSV and use insert_dataframe
        if file_format.lower() == "csv":
            df = pd.read_csv(file_path)
            return await self.insert_dataframe(table_name, df, if_exists="append")
        else:
            raise NotImplementedError(
                f"Bulk load for format '{file_format}' not implemented. "
                f"Override bulk_load() in subclass or use CSV format."
            )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
