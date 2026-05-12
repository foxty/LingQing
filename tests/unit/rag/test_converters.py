"""Tests for asset metadata text representation.

Tests the domain model's ability to generate searchable text for RAG indexing.
"""

from datetime import datetime, timezone

from apps.shared.data_source.domain import AssetMetadataDomain
from apps.shared.domain.value_objects import AssetMetaVO, ColumnVO, DataType


def test_asset_metadata_to_searchable_text_full():
    """Test text representation with all fields populated."""
    asset = AssetMetadataDomain(
        data_source_id=10,
        asset_name="users_table",
        asset_type="table",
        columns=[
            ColumnVO(name="id", data_type=DataType.INTEGER),
            ColumnVO(name="username", data_type=DataType.TEXT),
            ColumnVO(name="email", data_type=DataType.TEXT),
        ],
        row_count=1523,
        source_info={},
        meta=AssetMetaVO(description="User account information"),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        owner_id=1,
        id=1,
    )

    text = asset.to_searchable_text()

    assert "Data Asset: users_table" in text
    assert "Type: table" in text
    assert "Description: User account information" in text
    assert "Columns: id, username, email" in text
    assert "Row count: 1,523" in text


def test_asset_metadata_to_searchable_text_minimal():
    """Test text representation with minimal fields."""
    asset = AssetMetadataDomain(
        data_source_id=20,
        asset_name="simple_table",
        asset_type="view",
        columns=[],
        row_count=None,
        source_info={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        owner_id=1,
        id=2,
    )

    text = asset.to_searchable_text()

    assert "Data Asset: simple_table" in text
    assert "Type: view" in text
    # Should not contain optional fields
    assert "Description:" not in text
    assert "Columns:" not in text
    assert "Row count:" not in text


def test_asset_metadata_to_searchable_text_with_various_data_types():
    """Test text representation with different column data types."""
    asset = AssetMetadataDomain(
        data_source_id=10,
        asset_name="products",
        asset_type="table",
        columns=[
            ColumnVO(name="id", data_type=DataType.INTEGER),
            ColumnVO(name="name", data_type=DataType.TEXT),
            ColumnVO(name="price", data_type=DataType.FLOAT),
            ColumnVO(name="created_at", data_type=DataType.DATETIME),
            ColumnVO(name="is_active", data_type=DataType.BOOLEAN),
            ColumnVO(name="metadata", data_type=DataType.JSON),
        ],
        row_count=500,
        source_info={},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        meta=AssetMetaVO(
            description="Product catalog", column_description={"id": "this is the id", "name": "this is the name"}
        ),
        meta_override=AssetMetaVO(column_description={"name": "overridden name description"}),
        id=3,
        owner_id=1,
    )

    text = asset.to_searchable_text()

    assert "Data Asset: products" in text
    assert "Type: table" in text
    assert "Description: Product catalog" in text
    assert "Columns: id, name, price, created_at, is_active, metadata" in text
    assert "Row count: 500" in text
