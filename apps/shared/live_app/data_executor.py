"""Execution adapter for live app data operations."""

import json
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.data_source.adapters import db_data_source_to_domain
from apps.shared.data_source.repository import DataSourceRepository
from apps.shared.infra.analytics_db.manager_factory import get_db_manager_for_datasource
from apps.shared.utils.logger import get_logger
from apps.shared.utils.sql_utils import split_sql_script_statements

logger = get_logger(__name__)

_PG_TYPE_COERCIONS: dict[str, type | str] = {
    "integer": int,
    "bigint": int,
    "smallint": int,
    "serial": int,
    "bigserial": int,
    "numeric": Decimal,
    "decimal": Decimal,
    "real": float,
    "double precision": float,
    "boolean": "bool",
    "date": "date",
    "timestamp without time zone": "datetime",
    "timestamp with time zone": "datetime_tz",
    "time without time zone": "time",
    "time with time zone": "time",
    "uuid": "uuid",
    "json": "json",
    "jsonb": "json",
}


def _coerce_value(value: Any, pg_type: str) -> Any:
    """Coerce a Python value to match the expected PostgreSQL column type."""
    if value is None:
        return None

    coercion = _PG_TYPE_COERCIONS.get(pg_type)
    if coercion is None:
        return value

    if isinstance(coercion, type):
        if isinstance(value, coercion):
            return value
        try:
            return coercion(value)
        except (ValueError, TypeError, InvalidOperation):
            return value

    if coercion == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "t")
        return bool(value)

    if coercion == "date":
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value

    if coercion in ("datetime", "datetime_tz"):
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            dt = datetime.fromisoformat(value)
            if coercion == "datetime_tz" and dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        return value

    if coercion == "time":
        if isinstance(value, time):
            return value
        if isinstance(value, str):
            return time.fromisoformat(value)
        return value

    if coercion == "uuid":
        if isinstance(value, UUID):
            return value
        if isinstance(value, str):
            return UUID(value)
        return value

    if coercion == "json":
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return value

    return value


class LiveAppDataExecutor:
    """Low-level data execution for live apps using infra DB managers."""

    def __init__(self, tenant_id: int, db_session: AsyncSession):
        self.tenant_id = tenant_id
        self.data_source_repo = DataSourceRepository(db_session)

    async def _get_db_manager(self, data_source_id: int):
        data_source = await self.data_source_repo.get_by_id_and_tenant(data_source_id, self.tenant_id)
        if not data_source:
            raise ResourceNotFoundError(
                "Data source not found for live app.",
                details={"data_source_id": data_source_id},
            )
        domain = db_data_source_to_domain(data_source)
        return get_db_manager_for_datasource(domain)

    async def query_data(
        self,
        *,
        data_source_id: int,
        sql_query: str,
        params: dict[str, Any] | None = None,
        max_rows: int | None = None,
        schema_name: str | None = None,
    ) -> pd.DataFrame:
        db_manager = await self._get_db_manager(data_source_id)
        async with db_manager:
            if schema_name:
                await db_manager.execute(f'SET search_path TO "{schema_name}"')
            df = await db_manager.query(sql_query, params=params)

        if max_rows is not None and len(df) > max_rows:
            return df.head(max_rows)
        return df

    async def _get_column_types(
        self,
        db_manager: Any,
        schema: str,
        table: str,
    ) -> dict[str, str]:
        """Query information_schema for column name → data_type mapping."""
        df = await db_manager.query(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = :table",
            params={"schema": schema, "table": table},
        )
        return {str(row["column_name"]): str(row["data_type"]) for _, row in df.iterrows()}

    async def insert_rows(
        self,
        *,
        data_source_id: int,
        full_table_name: str,
        rows: list[dict[str, Any]],
    ) -> int:
        if not rows:
            return 0

        schema, table = full_table_name.split(".", maxsplit=1)
        columns = list(rows[0].keys())

        db_manager = await self._get_db_manager(data_source_id)
        async with db_manager:
            col_types = await self._get_column_types(db_manager, schema, table)

            params: dict[str, Any] = {}
            value_groups: list[str] = []
            for row_idx, row in enumerate(rows):
                if set(row.keys()) != set(columns):
                    raise ValueError("All rows must have identical keys for insert.")
                placeholders: list[str] = []
                for col in columns:
                    param_name = f"r{row_idx}_{col}"
                    pg_type = col_types.get(col, "")
                    params[param_name] = _coerce_value(row[col], pg_type)
                    placeholders.append(f":{param_name}")
                value_groups.append(f"({', '.join(placeholders)})")

            column_sql = ", ".join(f'"{col}"' for col in columns)
            sql = f'INSERT INTO "{schema}"."{table}" ({column_sql}) VALUES {", ".join(value_groups)}'
            return await db_manager.execute(sql, params=params)

    async def update_rows(
        self,
        *,
        data_source_id: int,
        full_table_name: str,
        data: dict[str, Any],
        where: dict[str, Any],
    ) -> int:
        if not data:
            raise ValueError("Update data cannot be empty.")
        if not where:
            raise ValueError("Update requires at least one WHERE condition.")

        schema, table = full_table_name.split(".", maxsplit=1)

        db_manager = await self._get_db_manager(data_source_id)
        async with db_manager:
            col_types = await self._get_column_types(db_manager, schema, table)

            params: dict[str, Any] = {}
            set_clauses: list[str] = []
            for col, val in data.items():
                param_name = f"s_{col}"
                params[param_name] = _coerce_value(val, col_types.get(col, ""))
                set_clauses.append(f'"{col}" = :{param_name}')

            where_clauses: list[str] = []
            for col, val in where.items():
                param_name = f"w_{col}"
                params[param_name] = _coerce_value(val, col_types.get(col, ""))
                where_clauses.append(f'"{col}" = :{param_name}')

            sql = (
                f'UPDATE "{schema}"."{table}" '
                f'SET {", ".join(set_clauses)} '
                f'WHERE {" AND ".join(where_clauses)}'
            )
            return await db_manager.execute(sql, params=params)

    async def update_by_id(
        self,
        *,
        data_source_id: int,
        full_table_name: str,
        row_id: int | str,
        data: dict[str, Any],
    ) -> int:
        if not data:
            raise ValueError("Update data cannot be empty.")

        schema, table = full_table_name.split(".", maxsplit=1)

        db_manager = await self._get_db_manager(data_source_id)
        async with db_manager:
            col_types = await self._get_column_types(db_manager, schema, table)

            params: dict[str, Any] = {"pk_id": _coerce_value(row_id, col_types.get("id", "integer"))}
            set_clauses: list[str] = []
            for col, val in data.items():
                param_name = f"s_{col}"
                params[param_name] = _coerce_value(val, col_types.get(col, ""))
                set_clauses.append(f'"{col}" = :{param_name}')

            sql = (
                f'UPDATE "{schema}"."{table}" '
                f'SET {", ".join(set_clauses)} '
                f'WHERE "id" = :pk_id'
            )
            return await db_manager.execute(sql, params=params)

    async def delete_by_id(
        self,
        *,
        data_source_id: int,
        full_table_name: str,
        row_id: int | str,
    ) -> int:
        schema, table = full_table_name.split(".", maxsplit=1)

        db_manager = await self._get_db_manager(data_source_id)
        async with db_manager:
            col_types = await self._get_column_types(db_manager, schema, table)
            params = {"pk_id": _coerce_value(row_id, col_types.get("id", "integer"))}
            sql = f'DELETE FROM "{schema}"."{table}" WHERE "id" = :pk_id'
            return await db_manager.execute(sql, params=params)

    async def import_csv(
        self,
        *,
        data_source_id: int,
        full_table_name: str,
        csv_file_path: str,
        mode: str = "append",
    ) -> int:
        db_manager = await self._get_db_manager(data_source_id)
        csv_path = Path(csv_file_path)
        async with db_manager:
            return await db_manager.import_csv(
                table_name=full_table_name,
                csv_path=csv_path,
                if_exists=mode,
            )

    async def ensure_schema(self, *, data_source_id: int, schema_name: str) -> None:
        logger.info(
            "Ensuring live app schema exists: tenant_id=%s, data_source_id=%s, schema=%s",
            self.tenant_id,
            data_source_id,
            schema_name,
        )
        db_manager = await self._get_db_manager(data_source_id)
        try:
            async with db_manager:
                await db_manager.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema_name}"')
        except Exception:
            logger.exception(
                "Failed ensuring live app schema: tenant_id=%s, data_source_id=%s, schema=%s",
                self.tenant_id,
                data_source_id,
                schema_name,
            )
            raise

        logger.info(
            "Ensured live app schema exists: tenant_id=%s, data_source_id=%s, schema=%s",
            self.tenant_id,
            data_source_id,
            schema_name,
        )

    async def list_applied_migrations(
        self,
        *,
        data_source_id: int,
        schema_name: str,
    ) -> list[dict[str, Any]]:
        migration_table = self._migration_table_name(schema_name=schema_name)
        db_manager = await self._get_db_manager(data_source_id)
        async with db_manager:
            await self._ensure_migration_table_exists(db_manager=db_manager, migration_table=migration_table)
            df = await db_manager.query(f"SELECT name, checksum, applied_at FROM {migration_table} ORDER BY name ASC")
        return [
            {
                "name": str(row["name"]),
                "checksum": str(row["checksum"]),
                "applied_at": None if pd.isna(row["applied_at"]) else str(row["applied_at"]),
            }
            for _, row in df.iterrows()
        ]

    async def apply_migration(
        self,
        *,
        data_source_id: int,
        schema_name: str,
        migration_name: str,
        checksum: str,
        up_sql: str,
    ) -> dict[str, Any]:
        migration_table = self._migration_table_name(schema_name=schema_name)
        db_manager = await self._get_db_manager(data_source_id)
        async with db_manager:
            await db_manager.execute(f'SET search_path TO "{schema_name}"')
            await self._ensure_migration_table_exists(db_manager=db_manager, migration_table=migration_table)
            existing_df = await db_manager.query(
                f"SELECT name, checksum FROM {migration_table} WHERE name = :name",
                params={"name": migration_name},
            )
            if not existing_df.empty:
                existing_checksum = str(existing_df.iloc[0]["checksum"])
                if existing_checksum == checksum:
                    return {"applied": False, "reason": "already_applied"}
                raise ValueError("Migration checksum mismatch with already applied migration.")
            up_parts = split_sql_script_statements(up_sql)
            if not up_parts:
                raise ValueError("Migration contains no executable SQL statements.")
            await db_manager.execute_transaction(
                [(stmt, None) for stmt in up_parts]
                + [
                    (
                        f"""
                        INSERT INTO {migration_table} (name, checksum)
                        VALUES (:name, :checksum)
                        """,
                        {"name": migration_name, "checksum": checksum},
                    ),
                ]
            )
        return {"applied": True, "reason": "applied"}

    async def rollback_migration(
        self,
        *,
        data_source_id: int,
        schema_name: str,
        migration_name: str,
        down_sql: str,
    ) -> dict[str, Any]:
        migration_table = self._migration_table_name(schema_name=schema_name)
        db_manager = await self._get_db_manager(data_source_id)
        async with db_manager:
            await db_manager.execute(f'SET search_path TO "{schema_name}"')
            await self._ensure_migration_table_exists(db_manager=db_manager, migration_table=migration_table)
            existing_df = await db_manager.query(
                f"SELECT name FROM {migration_table} WHERE name = :name",
                params={"name": migration_name},
            )
            if existing_df.empty:
                return {"rolled_back": False, "reason": "not_applied"}
            down_parts = split_sql_script_statements(down_sql)
            if not down_parts:
                raise ValueError("Rollback SQL contains no executable statements.")
            await db_manager.execute_transaction(
                [(stmt, None) for stmt in down_parts]
                + [(f"DELETE FROM {migration_table} WHERE name = :name", {"name": migration_name})]
            )
        return {"rolled_back": True, "reason": "rolled_back"}

    def _migration_table_name(self, *, schema_name: str) -> str:
        return f'"{schema_name}"."_applied_migrations"'

    async def _ensure_migration_table_exists(self, *, db_manager: Any, migration_table: str) -> None:
        await db_manager.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {migration_table} (
                name VARCHAR(255) PRIMARY KEY,
                checksum VARCHAR(128) NOT NULL,
                applied_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
