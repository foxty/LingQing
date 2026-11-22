"""HTTP CSV upload against provisioned managed analytics DB (httpx + savepoint session)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.db.models import AssetMetadata


@pytest.mark.asyncio
async def test_http_upload_csv_provisioned_analytics_db(
    async_db_session: AsyncSession,
    analytics_http_client,
    monkeypatch,
):
    monkeypatch.setattr("apps.config.EnvConfig.VECTOR_INDEXING_MODE", "async")

    client = analytics_http_client["client"]
    headers = analytics_http_client["headers"]
    data_source_id = analytics_http_client["stack"]["data_source_id"]
    suffix = uuid4().hex[:6]
    asset_name = f"orders_{suffix}"

    response = await client.post(
        f"/data-sources/{data_source_id}/assets/upload-csv",
        headers=headers,
        data={"asset_name": asset_name, "description": "httpx integration"},
        files={"file": (f"{asset_name}.csv", b"id,name\n1,alpha\n", "text/csv")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["row_count"] == 1
    assert body["asset_name"] == asset_name

    row = await async_db_session.execute(
        select(AssetMetadata).where(
            AssetMetadata.data_source_id == data_source_id,
            AssetMetadata.asset_name == asset_name,
        )
    )
    asset = row.scalar_one_or_none()
    assert asset is not None
    assert asset.row_count == 1