"""PostgreSQL-specific database manager with optimized bulk loading.

Extends RelationalDBManager to provide PostgreSQL-specific optimizations,
particularly COPY FROM for high-performance bulk loading of files.
"""

from pathlib import Path

from sqlalchemy import text

from apps.shared.data_source.domain import AssetMetadataDomain
from apps.shared.domain.value_objects import DatabaseConnectionVO
from apps.shared.infra.analytics_db.errors import QueryExecutionError
from apps.shared.infra.analytics_db.relational_db_manager import RelationalDBManager
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class PostgresManager(RelationalDBManager):
    """PostgreSQL-specific database manager.

    Extends RelationalDBManager with PostgreSQL-specific optimizations:
    - COPY FROM for high-performance bulk CSV loading
    - Native parameterized queries
    """

    def __init__(self, tenant_id: int, connection: DatabaseConnectionVO, managed: bool = False):
        """Initialize PostgreSQL manager.

        Args:
            tenant_id: Tenant ID
            connection: Database connection configuration
            managed: If True, allow write/DDL operations
        """
        super().__init__(tenant_id, connection, managed)

    async def bulk_load(
        self,
        table_name: str,
        file_path: Path,
        file_format: str = "csv",
        asset: AssetMetadataDomain | None = None,
    ) -> int:
        """Load CSV file directly into PostgreSQL using COPY FROM.

        This uses PostgreSQL's native COPY command for 10-100x faster
        bulk loading compared to regular INSERT statements.

        Args:
            table_name: Name of the target table
            file_path: Path to the CSV file
            file_format: File format (only 'csv' supported for COPY)
            asset: Asset metadata for table creation if needed

        Returns:
            Number of rows loaded

        Raises:
            PermissionError: If database is unmanaged
            FileNotFoundError: If file does not exist
            QueryExecutionError: If COPY fails
        """
        self._check_write_permission("bulk_load")

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if asset and not await self.table_exists(table_name):
            await self.create_table(asset)

        if file_format.lower() != "csv":
            # Fallback to parent for non-CSV formats
            return await super().bulk_load(table_name, file_path, file_format, asset)

        try:
            engine = self._get_engine()
            rows_loaded = 0

            async with engine.begin() as conn:
                # Use COPY FROM with file handle
                def _copy_from_file(sync_conn):
                    with open(file_path) as f:
                        # Read first line to detect headers
                        first_line = f.readline()
                        f.seek(0)

                        # Determine if CSV has headers
                        # Simple heuristic: if first line looks like column names, treat as header
                        has_header = not first_line[0].isdigit()

                        # Execute COPY command
                        copy_sql = f"COPY {table_name} FROM STDIN WITH (FORMAT csv, HEADER {has_header})"

                        raw_conn = sync_conn.connection
                        raw_conn.cursor().copy_expert(copy_sql, f)

                        # Get row count of loaded table
                        result = sync_conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                        return result.scalar() or 0

                rows_loaded = await conn.run_sync(_copy_from_file)

            logger.info(f"Bulk loaded {rows_loaded} rows into table '{table_name}' via COPY")
            return rows_loaded

        except Exception as e:
            logger.error(f"PostgreSQL COPY bulk load failed: {e}")
            raise QueryExecutionError(f"Failed to bulk load into '{table_name}': {str(e)}")
