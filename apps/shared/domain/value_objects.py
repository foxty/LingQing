from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

AssetTypeStr = Literal["table", "view", "materialized_view", "api_endpoint"]
DataSourceTypeStr = Literal["duckdb", "postgres", "mysql", "databricks", "snowflake", "bigquery"]
SQLDialectStr = Literal["postgres", "mysql", "databricks", "sqlite", "duckdb", "snowflake", "bigquery"]


class AssetType:
    """Asset types for data assets (Domain Value Object).

    Simple string constants for asset types. Using plain strings instead of Enum
    to reduce complexity and avoid serialization issues between layers.
    """

    TABLE = "table"
    VIEW = "view"
    MATERIALIZED_VIEW = "materialized_view"
    API_ENDPOINT = "api_endpoint"

    ALL_TYPES = frozenset([TABLE, VIEW, MATERIALIZED_VIEW, API_ENDPOINT])


class DataSourceType:
    """Data source types (Domain Value Object) - database providers.

    Simple string constants for database types. Using plain strings instead of Enum
    to reduce complexity and avoid serialization issues between layers.
    """

    SQLITE = "sqlite"
    DUCKDB = "duckdb"
    POSTGRES = "postgres"
    MYSQL = "mysql"
    DATABRICKS = "databricks"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"

    ALL_TYPES = frozenset([DUCKDB, POSTGRES, MYSQL, DATABRICKS, SNOWFLAKE, BIGQUERY])


def resolve_sql_dialect(data_source_type: str) -> SQLDialectStr | None:
    """Map data source type to SQL dialect used by query compiler.

    Returns None when the data source type is unknown.
    """
    if data_source_type in {
        DataSourceType.POSTGRES,
        DataSourceType.MYSQL,
        DataSourceType.DATABRICKS,
        DataSourceType.SQLITE,
        DataSourceType.DUCKDB,
        DataSourceType.SNOWFLAKE,
        DataSourceType.BIGQUERY,
    }:
        return data_source_type
    return None


class DataType(StrEnum):
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"
    DATE = "DATE"
    DATETIME = "DATETIME"
    JSON = "JSON"

    @classmethod
    def infer_from_pandas_dtype(cls, dtype_name: str) -> "DataType":
        """Infer DataType from pandas dtype string.

        Args:
            dtype_name: Pandas dtype string (e.g., 'int64', 'object', 'float32')

        Returns:
            Normalized DataType enum value
        """
        dtype_lower = dtype_name.lower()

        if "int" in dtype_lower:
            return cls.INTEGER
        elif "float" in dtype_lower:
            return cls.FLOAT
        elif "bool" in dtype_lower:
            return cls.BOOLEAN
        elif "datetime" in dtype_lower or "timestamp" in dtype_lower:
            return cls.DATETIME
        elif "date" in dtype_lower:
            return cls.DATE
        else:
            return cls.TEXT

    @classmethod
    def from_sql_type(cls, sql_type_str: str, dialect: str | None = None) -> "DataType":
        """Normalize SQL column type to DataType enum.

        Converts dialect-specific SQL types (e.g., 'bigint', 'VARCHAR(500)', 'TIMESTAMP')
        to canonical internal DataType enum values.

        Args:
            sql_type_str: SQL column type string (e.g., 'VARCHAR(500)', 'INTEGER', 'TIMESTAMP')
            dialect: Optional database dialect for dialect-specific handling (unused for now)

        Returns:
            Normalized DataType enum value
        """
        sql_type = sql_type_str.upper()

        # Integer types (INT, BIGINT, SERIAL, etc.)
        if any(t in sql_type for t in ["INT", "SERIAL", "BIGSERIAL", "SMALLSERIAL"]):
            return cls.INTEGER
        # Float types (FLOAT, REAL, DOUBLE, DECIMAL, NUMERIC)
        elif any(t in sql_type for t in ["FLOAT", "REAL", "DOUBLE", "DECIMAL", "NUMERIC"]):
            return cls.FLOAT
        # Text types (CHAR, TEXT, VARCHAR, CLOB, STRING)
        elif any(t in sql_type for t in ["CHAR", "TEXT", "VARCHAR", "CLOB", "STRING"]):
            return cls.TEXT
        # Boolean types
        elif "BOOL" in sql_type:
            return cls.BOOLEAN
        # Date/time types
        elif "TIMESTAMP" in sql_type or "DATETIME" in sql_type:
            return cls.DATETIME
        elif "DATE" in sql_type:
            return cls.DATE
        # JSON types
        elif "JSON" in sql_type or "BLOB" in sql_type:
            return cls.JSON
        else:
            # Default to TEXT for unknown types
            return cls.TEXT


@dataclass(frozen=True)
class DatabaseConnectionVO:
    """Database connection configuration (Domain Value Object).

    Unified representation for database connections. Supports two modes:
    1. Connection URL (compact): postgresql://user:pass@host:port/db
    2. Credentials (detailed): separate host, port, database, username, password

        For Databricks:
        - host: Databricks workspace hostname (e.g., adb-xxx.azuredatabricks.net)
        - password: Personal access token for authentication
        - extra_params: {warehouse_id or http_path, catalog, schema}
            - warehouse_id: SQL warehouse ID (required for REST Statement API)
            - http_path: SQL warehouse HTTP path (required for SQLAlchemy URL)
            - catalog: Optional default catalog name
            - schema: Optional default schema name

    One mode must be provided. If both exist, connection_url takes precedence.
    """

    connection_url: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password: str | None = None
    extra_params: dict[str, Any] | None = None

    def __post_init__(self):
        """Validate connection configuration based on detected datasource type."""
        # If connection_url provided, no credential validation needed
        if self.connection_url:
            return

        # Detect datasource type and validate accordingly
        if self._is_databricks_connection():
            self._validate_databricks()
        else:
            self._validate_standard_credentials()

    def _is_databricks_connection(self) -> bool:
        """Check if this appears to be a Databricks connection.

        Databricks connections have host but lack username/database fields.
        """
        return bool(self.host and not self.username and not self.database)

    def _validate_databricks(self) -> None:
        """Validate Databricks-specific connection requirements.

        Requires:
        - host: Databricks workspace hostname
        - password: Personal access token
        - extra_params['warehouse_id'] or extra_params['http_path']
        - extra_params['catalog'] and extra_params['schema']
        """
        if not self.password:
            raise ValueError("Databricks connection requires password (access token)")

        if not self.extra_params or not (self.extra_params.get("warehouse_id") or self.extra_params.get("http_path")):
            raise ValueError("Databricks connection requires extra_params with 'warehouse_id' or 'http_path'")

        if not self.extra_params.get("catalog") or not self.extra_params.get("schema"):
            raise ValueError("Databricks connection requires extra_params with 'catalog' and 'schema'")

    def _validate_standard_credentials(self) -> None:
        """Validate standard SQL database connection requirements.

        Requires either:
        - connection_url: Full database URL
        OR
        - host, database, username, password: Individual credentials
        """
        has_all_credentials = all([self.host, self.database, self.username, self.password])
        if not has_all_credentials:
            raise ValueError("Either provide connection_url or all of: host, database, username, password")

    def to_url(self, db_type: str = "postgresql") -> str:
        """Convert to connection URL format."""
        if self.connection_url:
            return self.connection_url

        driver_map = {
            "postgres": "postgresql+asyncpg",
            "postgresql": "postgresql+asyncpg",
            "mysql": "mysql+aiomysql",
            "sqlite": "sqlite+aiosqlite",
            "databricks": "databricks",
        }
        driver = driver_map.get(db_type, db_type)

        if db_type == "sqlite":
            return f"{driver}:///{self.database}"

        # Databricks uses a special connection format
        if db_type == "databricks":
            if not self.host or not self.password:
                raise ValueError("Databricks connection requires host (server_hostname) and password (access_token)")

            http_path = self.extra_params.get("http_path") if self.extra_params else None
            if not http_path:
                raise ValueError("Databricks connection requires http_path in extra_params")

            # Build catalog.schema path if provided
            # Note: warehouse_id is NOT included in URL; it's used by DatabricksManager's REST API only
            catalog = self.extra_params.get("catalog") if self.extra_params else None
            schema = self.extra_params.get("schema") if self.extra_params else None

            # URL format: databricks://token:<token>@<hostname>?http_path=<path>&catalog=<catalog>&schema=<schema>
            url = f"{driver}://token:{self.password}@{self.host}"
            url += f"?http_path={http_path}"
            if catalog:
                url += f"&catalog={catalog}"
            if schema:
                url += f"&schema={schema}"
            # Only include extra_params that are valid for the databricks URL (exclude warehouse_id)
            if self.extra_params:
                for key, value in self.extra_params.items():
                    if key not in ("http_path", "catalog", "schema", "warehouse_id"):
                        url += f"&{key}={value}"

            return url

        # Standard SQL database format
        port_str = f":{self.port}" if self.port else ""
        url = f"{driver}://{self.username}:{self.password}@{self.host}{port_str}/{self.database}"

        if self.extra_params:
            params = "&".join(f"{k}={v}" for k, v in self.extra_params.items())
            url += f"?{params}"

        return url

    def to_dict(self, include_sensitive: bool = True) -> dict[str, Any]:
        """Serialize to dictionary for storage."""
        data = {}
        if self.connection_url:
            data["connection_url"] = self.connection_url if include_sensitive else "***"
        if self.host:
            data["host"] = self.host
        if self.port:
            data["port"] = self.port
        if self.database:
            data["database"] = self.database
        if self.username:
            data["username"] = self.username
        if self.password:
            data["password"] = self.password if include_sensitive else "***"
        if self.extra_params:
            data["extra_params"] = self.extra_params
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatabaseConnectionVO":
        """Deserialize from dictionary."""
        return cls(
            connection_url=data.get("connection_url"),
            host=data.get("host"),
            port=data.get("port"),
            database=data.get("database") or data.get("db_name"),
            username=data.get("username") or data.get("user"),
            password=data.get("password"),
            extra_params=data.get("extra_params"),
        )

    @classmethod
    def from_url(cls, url: str, **extra_params) -> "DatabaseConnectionVO":
        """Create from connection URL."""
        return cls(
            connection_url=url,
            extra_params=extra_params or None,
        )

    @classmethod
    def from_credentials(
        cls,
        host: str,
        database: str,
        username: str,
        password: str,
        port: int | None = None,
        **extra_params,
    ) -> "DatabaseConnectionVO":
        """Create from separate credentials."""
        return cls(
            host=host,
            port=port,
            database=database,
            username=username,
            password=password,
            extra_params=extra_params or None,
        )


@dataclass(frozen=True)
class ColumnVO:
    name: str
    data_type: DataType
    raw_data_type: str | None = None  # Raw external type (e.g., "bigint", "varchar")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "data_type": self.data_type.value,
            "raw_data_type": self.raw_data_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ColumnVO":
        # Handle missing data_type for backward compatibility with old data
        data_type_str = data.get("data_type", "TEXT")
        return cls(
            name=data["name"],
            data_type=DataType(data_type_str),
            raw_data_type=data.get("raw_data_type"),
        )


@dataclass
class AssetMetaVO:
    description: str | None = None
    column_description: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.description:
            payload["description"] = self.description
        if self.column_description:
            payload["column_description"] = dict(self.column_description)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "AssetMetaVO":
        if not data:
            return cls()
        column_description = {key: value for key, value in (data.get("column_description") or {}).items() if value}
        return cls(
            description=data.get("description"),
            column_description=column_description,
        )

    def merge_over(self, override: "AssetMetaVO") -> "AssetMetaVO":
        description = override.description or self.description
        column_description = dict(self.column_description)
        column_description.update(override.column_description)
        return AssetMetaVO(description=description, column_description=column_description)
