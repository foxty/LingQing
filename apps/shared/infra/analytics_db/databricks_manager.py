"""Databricks SQL Warehouse manager using REST Statement Execution API.

Provides read-only access to Databricks Unity Catalog tables and views.
Uses the Databricks SQL Statement Execution API with true async I/O.
"""

import asyncio
import re
from datetime import UTC, datetime
from typing import Any

import aiohttp
import pandas as pd

from apps.config import EnvConfig
from apps.shared.data_source.schemas import DiscoveredAsset, DiscoveredColumn
from apps.shared.domain.value_objects import AssetType, DatabaseConnectionVO
from apps.shared.infra.analytics_db.errors import ConnectionError
from apps.shared.infra.analytics_db.relational_db_manager import RelationalDBManager
from apps.shared.utils.logger import get_logger


class DatabricksManager(RelationalDBManager):
    """Manager for Databricks SQL Warehouse connections via REST API.

    Extends RelationalDBManager to provide Databricks-specific functionality:
    - Uses REST Statement Execution API (true async)
    - Asset discovery via Unity Catalog INFORMATION_SCHEMA
    - Read-only access by default (managed=False)

    Connection configuration via DatabaseConnectionVO:
    - host: Databricks workspace hostname
    - password: Personal access token
    - extra_params: {warehouse_id or http_path, catalog (optional), schema (optional)}
    """

    def __init__(self, tenant_id: int, connection: DatabaseConnectionVO, managed: bool = False):
        """Initialize Databricks manager.

        Args:
            tenant_id: Tenant ID
            connection: DatabaseConnectionVO with Databricks connection details
            managed: If True, allow write operations (default: False for Databricks)

        Raises:
            ValueError: If required connection fields are missing
        """
        super().__init__(tenant_id, connection, managed)
        self.logger = get_logger(__name__, f"tenant:{tenant_id}:databricks")
        self._session: aiohttp.ClientSession | None = None
        self._base_url = self._normalize_host(connection.host)
        self._warehouse_id = None
        if connection.extra_params:
            self._warehouse_id = connection.extra_params.get("warehouse_id")
            if not self._warehouse_id and connection.extra_params.get("http_path"):
                self._warehouse_id = self._extract_warehouse_id(connection.extra_params.get("http_path"))
        self._catalog = connection.extra_params.get("catalog") if connection.extra_params else None
        self._schema = connection.extra_params.get("schema") if connection.extra_params else None

    @staticmethod
    def _normalize_host(host: str) -> str:
        if host.startswith("http://") or host.startswith("https://"):
            return host.rstrip("/")
        return f"https://{host}".rstrip("/")

    @staticmethod
    def _extract_warehouse_id(http_path: str | None) -> str | None:
        if not http_path:
            return None
        parts = [p for p in http_path.split("/") if p]
        return parts[-1] if parts else None

    async def _connect(self) -> None:
        if self._session is None or self._session.closed:
            headers = {
                "Authorization": f"Bearer {self.connection.password}",
                "Content-Type": "application/json",
            }
            timeout = aiohttp.ClientTimeout(total=60)
            self._session = aiohttp.ClientSession(headers=headers, timeout=timeout)
            self.logger.debug(f"Databricks REST session created for tenant {self.tenant_id}")

    async def _disconnect(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self.logger.debug(f"Databricks REST session closed for tenant {self.tenant_id}")
        self._session = None

    async def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        await self._connect()
        assert self._session is not None
        url = f"{self._base_url}{path}"
        async with self._session.request(method, url, json=payload) as response:
            data = await response.json()
            if response.status >= 400:
                message = data.get("message") or data.get("error") or str(data)
                raise ConnectionError(f"Databricks API error: {message}")
            return data

    async def _execute_sql(self, statement: str) -> list[list[Any]]:
        response = await self._execute_sql_response(statement)
        result = response.get("result", {})
        return result.get("data_array", [])

    async def _execute_sql_response(self, statement: str) -> dict[str, Any]:
        if not self._warehouse_id:
            raise ConnectionError("Databricks warehouse_id is required to execute statements")
        payload: dict[str, Any] = {
            "statement": statement,
            "warehouse_id": self._warehouse_id,
            "wait_timeout": "30s",
            "on_wait_timeout": "CONTINUE",
        }
        if self._catalog:
            payload["catalog"] = self._catalog
        if self._schema:
            payload["schema"] = self._schema

        response = await self._request("POST", "/api/2.0/sql/statements", payload)
        status = response.get("status", {})
        state = status.get("state")

        if state in {"PENDING", "RUNNING"}:
            statement_id = response.get("statement_id")
            response = await self._poll_statement(statement_id)

        status = response.get("status", {})
        state = status.get("state")
        if state != "SUCCEEDED":
            error = status.get("error", {})
            message = error.get("message") or str(error)
            raise ConnectionError(f"Databricks statement failed: {message}")

        return response

    @staticmethod
    def _extract_column_names(response: dict[str, Any]) -> list[str]:
        """Extract result column names from Databricks statement response."""
        result = response.get("result", {})

        schema_candidates = [
            result.get("schema"),
            result.get("manifest", {}).get("schema") if isinstance(result.get("manifest"), dict) else None,
            response.get("manifest", {}).get("schema") if isinstance(response.get("manifest"), dict) else None,
            response.get("schema"),
        ]

        for schema in schema_candidates:
            if not isinstance(schema, dict):
                continue
            columns = schema.get("columns")
            if not isinstance(columns, list):
                continue

            names: list[str] = []
            for idx, column in enumerate(columns):
                if isinstance(column, dict):
                    name = column.get("name") or column.get("column_name") or column.get("fieldName")
                    names.append(str(name) if name else f"col_{idx}")
                else:
                    names.append(f"col_{idx}")
            if names:
                return names

        return []

    async def _poll_statement(self, statement_id: str | None) -> dict[str, Any]:
        if not statement_id:
            raise ConnectionError("Databricks statement_id missing in response")

        for _ in range(60):
            await asyncio.sleep(1)
            response = await self._request("GET", f"/api/2.0/sql/statements/{statement_id}")
            status = response.get("status", {})
            state = status.get("state")
            if state in {"SUCCEEDED", "FAILED", "CANCELED"}:
                return response
        raise ConnectionError("Databricks statement did not complete in time")

    async def test_connection(self) -> tuple[bool, str]:
        """Test Databricks connection using REST API.

        Returns:
            Tuple of (success, message)
        """
        try:
            rows = await self._execute_sql("SELECT current_catalog() as catalog")
            catalog = rows[0][0] if rows else None

            if self._catalog and self._schema:
                safe_catalog = self._catalog.replace("'", "''")
                safe_schema = self._schema.replace("'", "''")
                validate_sql = f"""
                SELECT 1
                FROM system.information_schema.schemata
                WHERE catalog_name = '{safe_catalog}'
                  AND schema_name = '{safe_schema}'
                LIMIT 1
                """
                schema_rows = await self._execute_sql(validate_sql)
                if not schema_rows:
                    return False, f"Catalog/schema not found: {self._catalog}.{self._schema}"

            return True, f"Connection successful. Current catalog: {catalog}"
        except Exception as e:
            self.logger.error(f"Databricks connection test failed: {e}")
            return False, f"Connection failed: {str(e)}"

    async def query(self, sql: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
        """Execute a SQL query and return results as DataFrame.

        Uses REST Statement Execution API instead of SQLAlchemy.

        Args:
            sql: SQL query string
            params: Optional query parameters (note: Databricks API uses named parameters)

        Returns:
            Query results as DataFrame

        Raises:
            ConnectionError: If query execution fails
        """
        try:
            if params:
                sql = self._render_sql_with_params(sql, params)

            # Execute query via REST API
            response = await self._execute_sql_response(sql)
            result = response.get("result", {})
            rows = result.get("data_array", [])
            columns = self._extract_column_names(response)

            if rows:
                if columns and len(columns) == len(rows[0]):
                    df = pd.DataFrame(rows, columns=columns)
                else:
                    df = pd.DataFrame(rows)
            else:
                df = pd.DataFrame()

            return df
        except Exception as e:
            self.logger.error(f"Failed to execute query: {e}")
            raise ConnectionError(f"Query execution failed: {str(e)}")

    @staticmethod
    def _render_sql_with_params(sql: str, params: dict[str, Any]) -> str:
        """Render :named parameters to SQL literals for Databricks Statement API.

        Databricks Statement Execution API path used in this manager currently executes
        raw SQL text only. This renderer preserves the existing named parameter contract
        from services while ensuring values are safely escaped.
        """
        pattern = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")

        def replacer(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in params:
                raise ConnectionError(f"Missing query parameter: {key}")
            return DatabricksManager._to_sql_literal(params[key])

        return pattern.sub(replacer, sql)

    @staticmethod
    def _to_sql_literal(value: Any) -> str:
        if value is None:
            return "NULL"

        if isinstance(value, datetime):
            dt = value.astimezone(UTC) if value.tzinfo else value
            return f"'{dt.strftime('%Y-%m-%d %H:%M:%S')}'"

        if isinstance(value, (list, tuple, set)):
            items = list(value)
            if not items:
                return "NULL"
            return ", ".join(DatabricksManager._to_sql_literal(item) for item in items)

        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"

        if isinstance(value, (int, float)):
            return str(value)

        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"

    async def discover_assets(
        self,
        query: str | None = None,
        include_schema: bool = True,
    ) -> tuple[list[DiscoveredAsset], int]:
        """Discover tables and views from Unity Catalog.

        Queries INFORMATION_SCHEMA.TABLES via the Statement Execution API to discover all
        accessible tables and views. Returns fully qualified names in
        catalog.schema.table format.

        Args:
            query: Optional search query
            include_schema: Whether to include schema metadata

        Returns:
            Tuple of (assets, total)

        Raises:
            ValueError: If discovery fails
        """
        try:
            catalog_filter = self.connection.extra_params.get("catalog") if self.connection.extra_params else None
            schema_filter = self.connection.extra_params.get("schema") if self.connection.extra_params else None

            where_clauses = ["table_type IN ('BASE TABLE', 'MANAGED', 'EXTERNAL', 'VIEW')"]

            if catalog_filter:
                safe_catalog = catalog_filter.replace("'", "''")
                where_clauses.append(f"table_catalog = '{safe_catalog}'")
            if schema_filter:
                safe_schema = schema_filter.replace("'", "''")
                where_clauses.append(f"table_schema = '{safe_schema}'")

            if query:
                safe_query = query.replace("'", "''").lower()
                where_clauses.append(
                    f"(LOWER(table_name) LIKE '%{safe_query}%' OR LOWER(COALESCE(comment, '')) LIKE '%{safe_query}%')"
                )

            where_clause = " AND ".join(where_clauses)

            count_query = f"""
            SELECT COUNT(*)
            FROM system.information_schema.tables
            WHERE {where_clause}
            """
            count_rows = await self._execute_sql(count_query)
            total = count_rows[0][0] if count_rows else 0

            limit_clause = f"LIMIT {EnvConfig.DISCOVERY_ASSET_LIMIT}"

            query_sql = f"""
            SELECT
                table_catalog,
                table_schema,
                table_name,
                table_type,
                comment
            FROM system.information_schema.tables
            WHERE {where_clause}
            ORDER BY table_catalog, table_schema, table_name
            {limit_clause}
            """

            rows = await self._execute_sql(query_sql)

            assets: list[DiscoveredAsset] = []
            for row in rows:
                catalog, schema, table, table_type, comment = row
                qualified_name = f"{catalog}.{schema}.{table}"

                if table_type in ("BASE TABLE", "MANAGED", "EXTERNAL"):
                    asset_type = AssetType.TABLE
                elif table_type == "VIEW":
                    asset_type = AssetType.VIEW
                else:
                    asset_type = AssetType.TABLE

                if include_schema:
                    asset = await self._build_discovered_asset(qualified_name, asset_type)
                    if asset:
                        if comment and not asset.description:
                            asset = DiscoveredAsset(
                                name=asset.name,
                                type=asset.type,
                                row_count=asset.row_count,
                                description=comment,
                                columns=asset.columns,
                            )
                        assets.append(asset)
                else:
                    assets.append(
                        DiscoveredAsset(
                            name=qualified_name,
                            type=asset_type,
                            row_count=None,
                            description=comment,
                            columns=None,
                        )
                    )

            self.logger.info(f"Discovered {len(assets)} assets from Databricks")
            return assets, total

        except Exception as e:
            self.logger.error(f"Databricks asset discovery failed: {e}")
            raise ValueError(f"Failed to discover assets: {str(e)}")

    async def discover_asset(self, asset_name: str, *, include_row_count: bool = True) -> DiscoveredAsset | None:
        """Discover a specific asset by name using Unity Catalog metadata."""
        try:
            parts = asset_name.split(".")
            if len(parts) >= 3:
                catalog, schema, table = parts[0], parts[1], parts[-1]
            else:
                catalog, schema, table = None, None, asset_name

            where_clauses = ["table_type IN ('BASE TABLE', 'MANAGED', 'EXTERNAL', 'VIEW')"]

            safe_table = table.replace("'", "''")
            where_clauses.append(f"table_name = '{safe_table}'")

            if catalog:
                safe_catalog = catalog.replace("'", "''")
                where_clauses.append(f"table_catalog = '{safe_catalog}'")
            if schema:
                safe_schema = schema.replace("'", "''")
                where_clauses.append(f"table_schema = '{safe_schema}'")

            where_clause = " AND ".join(where_clauses)

            query_sql = f"""
            SELECT
                table_catalog,
                table_schema,
                table_name,
                table_type,
                comment
            FROM system.information_schema.tables
            WHERE {where_clause}
            LIMIT 1
            """

            rows = await self._execute_sql(query_sql)
            if not rows:
                return None

            catalog, schema, table, table_type, comment = rows[0]
            qualified_name = f"{catalog}.{schema}.{table}"

            if table_type in ("BASE TABLE", "MANAGED", "EXTERNAL"):
                asset_type = AssetType.TABLE
            elif table_type == "VIEW":
                asset_type = AssetType.VIEW
            else:
                asset_type = AssetType.TABLE

            asset = await self._build_discovered_asset(
                qualified_name,
                asset_type,
                include_row_count=include_row_count,
            )
            if asset and comment and not asset.description:
                asset = DiscoveredAsset(
                    name=asset.name,
                    type=asset.type,
                    row_count=asset.row_count,
                    description=comment,
                    columns=asset.columns,
                )
            return asset

        except Exception as e:
            self.logger.error(f"Databricks asset discovery failed for '{asset_name}': {e}")
            raise ValueError(
                f"Failed to discover asset '{asset_name}': {self._format_exception_message(e)}"
            )

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
        """Build discovered asset metadata for a Databricks table or view.

        Args:
            asset_name: Fully qualified name (catalog.schema.table)
            asset_type: Type of asset (TABLE or VIEW)

        Returns:
            DiscoveredAsset with metadata, or None if metadata retrieval fails
        """
        try:
            # Extract table name from fully qualified name
            parts = asset_name.split(".")
            catalog = parts[0] if len(parts) > 2 else None
            schema = parts[1] if len(parts) > 2 else None
            table = parts[-1] if parts else asset_name

            # Get columns from system.information_schema (Databricks Unity Catalog)
            column_query = """
            SELECT 
                column_name,
                data_type,
                comment
            FROM system.information_schema.columns
            WHERE table_name = :table_name
            ORDER BY ordinal_position
            """

            safe_table = table.replace("'", "''")
            column_where = [f"table_name = '{safe_table}'"]
            if catalog:
                safe_catalog = catalog.replace("'", "''")
                column_where.append(f"table_catalog = '{safe_catalog}'")
            if schema:
                safe_schema = schema.replace("'", "''")
                column_where.append(f"table_schema = '{safe_schema}'")

            column_query = column_query.replace("WHERE table_name = :table_name", "WHERE " + " AND ".join(column_where))

            column_rows = await self._execute_sql(column_query)

            # Get row count for tables only (skip for views - can be expensive)
            row_count = None

            if include_row_count:
                try:
                    quoted_name = self._quote_identifier(asset_name)
                    count_rows = await self._execute_sql(f"SELECT COUNT(*) FROM {quoted_name}")
                    row_count = count_rows[0][0] if count_rows else None
                except Exception as e:
                    self.logger.warning(f"Failed to get row count for {asset_name}: {e}")

            columns = [
                DiscoveredColumn(
                    name=col[0],
                    data_type=col[1],
                    comment=col[2],
                )
                for col in column_rows
            ]

            return DiscoveredAsset(
                name=asset_name,
                type=asset_type,
                row_count=row_count,
                description=None,  # Will be set from INFORMATION_SCHEMA.TABLES if available
                columns=columns if columns else None,
            )

        except Exception as e:
            self.logger.warning(f"Failed to get metadata for Databricks asset {asset_name}: {e}")
            # Return basic asset info even if detailed metadata fails
            return DiscoveredAsset(
                name=asset_name,
                type=asset_type,
                row_count=None,
                columns=None,
            )

    @staticmethod
    def _quote_identifier(name: str) -> str:
        parts = [part.strip("`") for part in name.split(".") if part]
        return ".".join(f"`{part}`" for part in parts)
