"""SQL type normalization utility for mapping dialect-specific types to DataType enum."""

from apps.shared.domain.value_objects import DataType
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class SQLTypeMapper:
    """Maps SQL column types from various dialects to canonical DataType enum values."""

    @staticmethod
    def normalize(sql_type_str: str, dialect: str | None = None) -> str:
        """Normalize SQL type string to DataType enum value.

        Args:
            sql_type_str: SQL column type string (e.g., 'VARCHAR(500)', 'INTEGER', 'TIMESTAMP')
            dialect: Optional database dialect for dialect-specific handling

        Returns:
            Normalized DataType enum value as string
        """
        sql_type = sql_type_str.upper()

        # Integer types
        if any(t in sql_type for t in ["INT", "SERIAL", "BIGSERIAL", "SMALLSERIAL"]):
            return DataType.INTEGER.value
        # Float types
        elif any(t in sql_type for t in ["FLOAT", "REAL", "DOUBLE", "DECIMAL", "NUMERIC"]):
            return DataType.FLOAT.value
        # Text types
        elif any(t in sql_type for t in ["CHAR", "TEXT", "VARCHAR", "CLOB", "STRING"]):
            return DataType.TEXT.value
        # Boolean types
        elif "BOOL" in sql_type:
            return DataType.BOOLEAN.value
        # Date/time types
        elif "TIMESTAMP" in sql_type or "DATETIME" in sql_type:
            return DataType.DATETIME.value
        elif "DATE" in sql_type:
            return DataType.DATE.value
        # JSON types
        elif "JSON" in sql_type or "BLOB" in sql_type:
            return DataType.JSON.value
        else:
            # Default to TEXT for unknown types
            logger.debug(f"Unknown SQL type '{sql_type_str}', defaulting to TEXT")
            return DataType.TEXT.value
