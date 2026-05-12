"""Domain models for data_source module."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from apps.shared.domain.base_domain_model import BaseDomainModel
from apps.shared.domain.value_objects import (
    AssetMetaVO,
    AssetType,
    AssetTypeStr,
    ColumnVO,
    DatabaseConnectionVO,
    DataSourceTypeStr,
)

SQL_DIALECT_HINTS = {
    "postgres": {
        "date_format": "TO_CHAR(column, 'YYYY-MM')",
        "date_extract": "EXTRACT(YEAR FROM column)",
        "string_concat": "column1 || column2",
        "limit": "LIMIT n",
    },
    "mysql": {
        "date_format": "DATE_FORMAT(column, '%Y-%m')",
        "date_extract": "YEAR(column)",
        "string_concat": "CONCAT(column1, column2)",
        "limit": "LIMIT n",
    },
}


@dataclass
class DataSourceDomain(BaseDomainModel):
    """Data source domain model for analytics databases."""

    id: int
    tenant_id: int
    name: str
    type: DataSourceTypeStr
    managed: bool
    connection: DatabaseConnectionVO
    description: str | None
    owner_id: int
    asset_count: int
    created_at: datetime
    updated_at: datetime
    owner_name: str | None = None
    assets: list["AssetMetadataDomain"] = field(default_factory=list)

    def is_managed(self) -> bool:
        """Check if data source is managed by platform."""
        return self.managed

    def has_assets(self) -> bool:
        """Check if data source has any assets."""
        return self.asset_count > 0

    def to_llm_text(self) -> str:
        """Convert data source to text for RAG indexing or LLM to detect SQL dialect."""
        text = f"Data Source: {self.name} (type: {self.type})\n"
        if self.description:
            text += f"Description: {self.description}\n"
        text += f"TIPS: The generated SQL for this data source should compatible with the database type : {self.type}\n"
        text += f"SQL Dialect Hints: {SQL_DIALECT_HINTS.get(self.type.lower(), '')}"
        return text


@dataclass
class AssetMetadataDomain(BaseDomainModel):
    data_source_id: int
    asset_name: str
    asset_type: AssetTypeStr  # Support both AssetType enum and str for backward compatibility
    columns: list[ColumnVO]
    row_count: int | None
    source_info: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    owner_id: int
    owner_name: str | None = None
    id: int | None = None
    # Sync status fields - track metadata synchronization
    last_metadata_synced_at: datetime | None = None
    last_metadata_sync_error: str | None = None
    # Vector sync status fields from ResourceIndex
    vector_synced_at: datetime | None = None
    vector_sync_error: str | None = None
    vector_sync_error_at: datetime | None = None
    meta: AssetMetaVO = field(default_factory=AssetMetaVO)
    meta_override: AssetMetaVO = field(default_factory=AssetMetaVO)

    def is_table(self) -> bool:
        return self.asset_type == AssetType.TABLE

    def is_view(self) -> bool:
        return self.asset_type == AssetType.VIEW

    def get_column_names(self) -> list[str]:
        return [col.name for col in self.columns]

    def get_column(self, name: str) -> ColumnVO | None:
        return next((col for col in self.columns if col.name == name), None)

    def has_data(self) -> bool:
        return self.row_count is not None and self.row_count > 0

    def is_persisted(self) -> bool:
        return self.id is not None

    def resolved_meta(self) -> AssetMetaVO:
        return self.meta.merge_over(self.meta_override)

    def resolved_description(self) -> str | None:
        return self.resolved_meta().description

    def resolved_columns(self) -> list[dict[str, Any]]:
        """Return columns with resolved descriptions for API/search use."""
        meta = self.resolved_meta()
        column_description = meta.column_description or {}
        resolved = []
        for col in self.columns:
            col_dict = col.to_dict()
            col_dict["description"] = column_description.get(col.name)
            resolved.append(col_dict)
        return resolved

    def to_dict(self) -> dict[str, Any]:
        """Convert domain model to dictionary for serialization."""
        return {
            "asset_id": self.id,
            "data_source_id": self.data_source_id,
            "asset_name": self.asset_name,
            "asset_type": self.asset_type,
            "columns": [col.to_dict() for col in self.columns],
            "row_count": self.row_count,
            "description": self.resolved_description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_searchable_text(self) -> str:
        """Lightweight text for vector search (table-level meta + column names only).

        Two-stage retrieval: vector DB finds the right asset by name/description,
        then the agent fetches full column details for SQL generation.

        Example:
            Data Asset: chat_messages
            Type: table
            Description: Stores all chat messages for agents.
            Row count: 638
            Columns: id, message_id, content, is_summarized
        """
        text_parts = [
            f"Data Asset: {self.asset_name}",
            f"Type: {self.asset_type}",
        ]
        if resolved_description := self.resolved_description():
            text_parts.append(f"Description: {resolved_description}")
        if self.row_count is not None:
            text_parts.append(f"Row count: {self.row_count:,}")
        if self.columns:
            text_parts.append(f"Columns: {', '.join(col.name for col in self.columns)}")

        return "\n".join(text_parts)

    # ========== Factory Methods (DDD Pattern) ==========

    @classmethod
    def create_new(
        cls,
        data_source_id: int,
        asset_name: str,
        asset_type: AssetType | str,
        columns: list[ColumnVO],
        *,
        owner_id: int,
        row_count: int | None = None,
        source_info: dict[str, Any] | None = None,
        meta: AssetMetaVO | None = None,
        meta_override: AssetMetaVO | None = None,
    ) -> "AssetMetadataDomain":
        """Factory method to create a new asset metadata (DDD pattern).

        This method encapsulates the creation logic including:
        - Setting timestamps
        - Default values

        Args:
            data_source_id: Data source ID
            asset_name: Asset name
            asset_type: Asset type (TABLE, VIEW, etc.)
            columns: List of column value objects
            row_count: Optional row count
            source_info: Optional source info dict
            meta: Optional synced metadata payload
            meta_override: Optional user override payload

        Returns:
            New AssetMetadataDomain instance ready for persistence
        """
        if meta is None:
            meta = AssetMetaVO()

        return cls(
            id=None,  # Not persisted yet
            data_source_id=data_source_id,
            asset_name=asset_name,
            asset_type=asset_type,
            columns=columns,
            row_count=row_count,
            source_info=source_info or {},
            meta=meta or AssetMetaVO(),
            meta_override=meta_override or AssetMetaVO(),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            owner_id=owner_id,
            # Sync status - initialized to reflect creation as metadata sync point
            last_metadata_synced_at=datetime.now(UTC),
            last_metadata_sync_error=None,
        )

    @classmethod
    def from_dataframe_schema(
        cls,
        data_source_id: int,
        asset_name: str,
        column_metadata: list[tuple[str, str]],
        *,
        owner_id: int,
        row_count: int = 0,
        asset_type: str = AssetType.TABLE,
        source_info: dict[str, Any] | None = None,
        meta: AssetMetaVO | None = None,
    ) -> "AssetMetadataDomain":
        """Factory method to create asset from DataFrame schema.

        Args:
            data_source_id: Data source ID
            asset_name: Asset name
            column_metadata: List of (column_name, dtype_string) tuples
            row_count: Row count
            asset_type: Asset type
            source_info: Optional source info
            meta: Optional synced metadata payload

        Returns:
            New AssetMetadataDomain instance
        """
        from apps.shared.domain.value_objects import DataType

        columns = [
            ColumnVO(
                name=col_name,
                data_type=DataType.infer_from_pandas_dtype(dtype_str),
                raw_data_type=dtype_str,  # Preserve raw pandas dtype string
            )
            for col_name, dtype_str in column_metadata
        ]

        return cls.create_new(
            data_source_id=data_source_id,
            asset_name=asset_name,
            asset_type=asset_type,
            columns=columns,
            row_count=row_count,
            source_info=source_info,
            meta=meta,
            owner_id=owner_id,
        )
