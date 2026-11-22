"""Agent database tools against real provisioned analytics PostgreSQL (no DB manager mocks)."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest
from sqlalchemy import select

from apps.shared.db.models import AssetMetadata
from apps.shared.external_systems.data_source.asset_metadata_service import AssetMetadataService
from apps.tenant_app_service.agents.domain import AgentRuntimeContext, AgentTenantContext, AgentUserContext
from apps.tenant_app_service.agents.tools import database as database_tool
from tests.integration.test_database_tool_integration import _SessionContext
from tests.integration.tool_integration_helpers import build_runnable_config_for_actor


@pytest.mark.asyncio
async def test_run_sql_query_on_datasource_uses_provisioned_analytics_db(
    async_db_session,
    provisioned_analytics_stack,
    monkeypatch,
):
    """``run_sql_query_on_datasource`` end-to-end with URL-encoded managed analytics credentials."""
    monkeypatch.setattr("apps.config.EnvConfig.VECTOR_INDEXING_MODE", "async")
    monkeypatch.setattr(database_tool, "app_db_session", lambda: _SessionContext(async_db_session))

    stack = provisioned_analytics_stack
    tenant_id = stack["tenant_id"]
    data_source_id = stack["data_source_id"]
    user = stack["user"]
    actor = stack["actor"]

    asset_service = AssetMetadataService(tenant_id=tenant_id, db_session=async_db_session)
    ds_service = stack["ds_service"]

    with NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
        temp_file.write(b"id,label\n1,agent_row\n")
        csv_path = Path(temp_file.name)

    try:
        db_manager = await ds_service.get_db_manager_for_actor(data_source_id, actor)
        async with db_manager as db:
            await asset_service.import_csv_as_asset_for_actor(
                actor=actor,
                data_source_id=data_source_id,
                asset_name="agent_probe",
                file_name="agent_probe.csv",
                csv_path=csv_path,
                db_manager=db,
            )
    finally:
        csv_path.unlink(missing_ok=True)

    runtime = AgentRuntimeContext(
        tenant=AgentTenantContext(tenant_id=tenant_id, tenant_name=stack["tenant_name"], config={}),
        user=AgentUserContext(
            user_id=user.id,
            username=user.username,
            role=user.role,
            tenant_id=tenant_id,
            tenant_name=stack["tenant_name"],
        ),
        agent_id=9001,
        agent_name="probe_agent",
        thread_id="thread-analytics-db-probe",
        session_id="session-analytics-db-probe",
    )
    runnable_config = build_runnable_config_for_actor(
        runtime,
        user_id=user.id,
        username=user.username,
        role=user.role,
        thread_id=runtime.thread_id,
    )

    result = await database_tool.run_sql_query_on_datasource.ainvoke(
        {
            "data_source_id": data_source_id,
            "sql_query": "SELECT id, label FROM agent_probe",
        },
        config=runnable_config,
    )
    payload = json.loads(result.content)
    assert payload.get("error") is None
    assert payload["row_count"] == 1
    assert payload["rows"][0]["label"] == "agent_row"

    asset_row = await async_db_session.execute(
        select(AssetMetadata).where(
            AssetMetadata.data_source_id == data_source_id,
            AssetMetadata.asset_name == "agent_probe",
        )
    )
    assert asset_row.scalar_one_or_none() is not None