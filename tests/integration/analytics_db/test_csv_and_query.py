"""CSV import and SQL query against provisioned managed analytics databases."""

from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.external_systems.data_source.asset_metadata_service import AssetMetadataService


@pytest.mark.asyncio
async def test_csv_import_into_provisioned_analytics_db(
    async_db_session: AsyncSession,
    provisioned_analytics_stack,
    monkeypatch,
):
    monkeypatch.setattr("apps.config.EnvConfig.VECTOR_INDEXING_MODE", "async")

    tenant_id = provisioned_analytics_stack["tenant_id"]
    data_source_id = provisioned_analytics_stack["data_source_id"]
    actor = provisioned_analytics_stack["actor"]
    asset_service = AssetMetadataService(tenant_id=tenant_id, db_session=async_db_session)
    ds_service = provisioned_analytics_stack["ds_service"]

    with NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
        temp_file.write(b"id,sku\n10,widget_a\n20,widget_b\n")
        csv_path = Path(temp_file.name)

    try:
        db_manager = await ds_service.get_db_manager_for_actor(data_source_id, actor)
        async with db_manager as db:
            asset, rows = await asset_service.import_csv_as_asset_for_actor(
                actor=actor,
                data_source_id=data_source_id,
                asset_name="sku_upload",
                file_name="sku.csv",
                csv_path=csv_path,
                db_manager=db,
                description="integration sku table",
            )
        assert rows == 2
        assert asset.asset_name == "sku_upload"
    finally:
        csv_path.unlink(missing_ok=True)

    df = await ds_service.query_data_for_actor(
        data_source_id,
        "SELECT id, sku FROM sku_upload ORDER BY id",
        actor=actor,
    )
    assert len(df) == 2
    assert df.iloc[0]["sku"] == "widget_a"