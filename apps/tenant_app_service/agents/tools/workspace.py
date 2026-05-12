"""Workspace tools for materialized views and cross-datasource operations.

Provides advanced data management capabilities:
- Materialized views for large query results
- Cross-datasource JOIN operations
- Temporary table management

These tools are legacy non-API paths and are kept for backward compatibility.
"""

from datetime import UTC, datetime

import pandas as pd
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.shared.data_source import DataSourceService
from apps.shared.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import delegated_data_source_ids, extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolResult
from apps.tenant_app_service.agents.workspace_utils import (
    cleanup_temp_tables_for_thread,
    generate_temp_table_name,
    get_managed_datasource,
    list_temp_tables_for_thread,
    register_temp_table,
)

logger = get_logger(__name__)


@tool
async def create_materialized_view(
    data_source_id: int,
    sql_query: str,
    view_name: str,
    description: str = None,
    config: RunnableConfig = None,
) -> ToolResult:
    """Create a materialized view (temporary table) in the managed data source.

    Legacy path: this capability is intentionally not exposed as a platform REST API yet
    and is planned for future deprecation in agent workflows.

    **Use Cases:**
    - Query result > 1000 rows
    - Need to reuse result multiple times
    - Complex JOIN or aggregation to cache

    **Benefits:**
    - Data stays in source database
    - Query repeatedly without re-execution
    - Auto-cleanup after 24 hours

    Args:
        data_source_id: Source data source ID
        sql_query: SELECT query to materialize
        view_name: Name for the view (auto-prefixed with _temp_)
        description: Optional description
        config: Runtime configuration

    Returns:
        JSON with view metadata

    Example:
        create_materialized_view(
            data_source_id=1,
            sql_query="SELECT * FROM orders WHERE year=2024",
            view_name="orders_2024"
        )
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id
    user_id = runtime.user.user_id
    user_role = runtime.user.role
    thread_id = runtime.thread_id
    actor = ActorContext(
        tenant_id=tenant_id,
        user_id=user_id,
        user_role=user_role,
    )

    try:
        async with app_db_session() as session:
            service = DataSourceService(
                tenant_id=tenant_id,
                data_source_repo=DataSourceRepository(session),
                asset_repo=AssetMetadataRepository(session),
            )

            # Get data source info for validation
            data_source = await service.get_data_source_for_actor(
                data_source_id=data_source_id,
                actor=actor,
            )

            if not data_source:
                return ToolResult.error_result(
                    code="WORKSPACE_DATASOURCE_NOT_FOUND",
                    message=f"Data source {data_source_id} not found",
                )

            if not data_source.managed:
                return ToolResult.error_result(
                    code="WORKSPACE_UNMANAGED_DATASOURCE",
                    message=(
                        f"Cannot create materialized view in non-managed datasource '{data_source.name}'. "
                        "Only the managed datasource supports write operations. "
                        "Use join_cross_datasource() to import aggregated data to managed datasource first."
                    ),
                )

            temp_table_name = generate_temp_table_name(thread_id, view_name)

            # Execute read query via auth-aware service path
            df = await service.query_data_for_actor(
                data_source_id=data_source_id,
                sql_query=sql_query,
                actor=actor,
                delegated_ids=delegated_data_source_ids(runtime.capability_profile),
            )

            # Get DB manager through service for write operation
            db_manager = await service.get_db_manager(data_source_id)
            async with db_manager:
                total_rows = len(df)
                await db_manager.insert_dataframe(temp_table_name, df, if_exists="replace")

            logger.info(
                f"Created materialized view '{temp_table_name}' with {total_rows} rows in data source {data_source_id}"
            )

            await register_temp_table(
                session=session,
                tenant_id=tenant_id,
                thread_id=thread_id,
                data_source_id=data_source_id,
                table_name=temp_table_name,
                meta_info={
                    "type": "materialized_view",
                    "source_query": sql_query,
                    "row_count": total_rows,
                    "columns": df.columns.tolist(),
                    "description": description,
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )

            sample_rows = df.head(5).to_dict(orient="records")

            return ToolResult.success(
                {
                    "status": "success",
                    "view_name": temp_table_name,
                    "data_source_id": data_source_id,
                    "data_source_name": data_source.name,
                    "row_count": total_rows,
                    "columns": df.columns.tolist(),
                    "sample_rows": sample_rows,
                    "message": (
                        f"✅ Materialized view '{temp_table_name}' created with {total_rows} rows.\n"
                        f"Query using: run_sql_query_on_datasource({data_source_id}, 'SELECT ... FROM {temp_table_name}')\n"
                        f"View expires in 24 hours."
                    ),
                }
            )

    except Exception as e:
        logger.error(f"Error creating materialized view: {e}", exc_info=True)
        return ToolResult.error_result(
            code="WORKSPACE_CREATE_MATERIALIZED_VIEW_FAILED",
            message=str(e),
        )


@tool
async def join_cross_datasource(
    left_data_source_id: int,
    left_query: str,
    right_data_source_id: int,
    right_query: str,
    join_type: str,
    left_on: str,
    right_on: str,
    result_name: str = "joined_result",
    config: RunnableConfig = None,
) -> ToolResult:
    """Join data from TWO DIFFERENT data sources.

    Legacy path: this capability is intentionally not exposed as a platform REST API yet
    and is planned for future deprecation in agent workflows.

    **Only use when:**
    - Data is in different databases
    - Cannot use SQL JOIN directly

    **For same data source:** Use regular SQL JOIN instead!

    Args:
        left_data_source_id: Left table data source ID
        left_query: SQL to extract left table
        right_data_source_id: Right table data source ID
        right_query: SQL to extract right table
        join_type: 'inner', 'left', 'right', 'outer'
        left_on: Join key in left table
        right_on: Join key in right table
        result_name: Name for result table
        config: Runtime configuration

    Returns:
        JSON with result metadata

    Example:
        join_cross_datasource(
            left_data_source_id=2,
            left_query="SELECT customer_id, SUM(amount) as revenue FROM orders GROUP BY customer_id",
            right_data_source_id=1,
            right_query="SELECT id, name, region FROM customers",
            join_type="left",
            left_on="customer_id",
            right_on="id",
            result_name="customer_revenue"
        )
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id
    user_id = runtime.user.user_id
    user_role = runtime.user.role
    thread_id = runtime.thread_id
    actor = ActorContext(
        tenant_id=tenant_id,
        user_id=user_id,
        user_role=user_role,
    )

    try:
        async with app_db_session() as session:
            service = DataSourceService(
                tenant_id=tenant_id,
                data_source_repo=DataSourceRepository(session),
                asset_repo=AssetMetadataRepository(session),
            )

            # Extract left table
            attached_ids = delegated_data_source_ids(runtime.capability_profile)
            left_ds = await service.get_data_source_for_actor(
                data_source_id=left_data_source_id,
                actor=actor,
                delegated_ids=attached_ids,
            )

            if not left_ds:
                return ToolResult.error_result(
                    code="WORKSPACE_LEFT_DATASOURCE_NOT_FOUND",
                    message=f"Left data source {left_data_source_id} not found",
                )

            left_df = await service.query_data_for_actor(
                data_source_id=left_data_source_id,
                sql_query=left_query,
                actor=actor,
                delegated_ids=attached_ids,
            )

            logger.info(f"Extracted {len(left_df)} rows from left source '{left_ds.name}'")

            # Extract right table
            right_ds = await service.get_data_source_for_actor(
                data_source_id=right_data_source_id,
                actor=actor,
                delegated_ids=attached_ids,
            )

            if not right_ds:
                return ToolResult.error_result(
                    code="WORKSPACE_RIGHT_DATASOURCE_NOT_FOUND",
                    message=f"Right data source {right_data_source_id} not found",
                )

            right_df = await service.query_data_for_actor(
                data_source_id=right_data_source_id,
                sql_query=right_query,
                actor=actor,
                delegated_ids=attached_ids,
            )

            logger.info(f"Extracted {len(right_df)} rows from right source '{right_ds.name}'")

            # Perform join
            result_df = pd.merge(left_df, right_df, left_on=left_on, right_on=right_on, how=join_type)
            total_rows = len(result_df)

            logger.info(f"Join produced {total_rows} rows")

            # Get managed DB as workspace
            analytics_db = await get_managed_datasource(tenant_id, session)

            # Save to workspace
            temp_table_name = generate_temp_table_name(thread_id, result_name)

            workspace_db_manager = await service.get_db_manager(analytics_db.id)
            async with workspace_db_manager:
                await workspace_db_manager.insert_dataframe(temp_table_name, result_df, if_exists="replace")

            logger.info(f"Stored join result in workspace: '{temp_table_name}' ({total_rows} rows)")

            await register_temp_table(
                session=session,
                tenant_id=tenant_id,
                thread_id=thread_id,
                data_source_id=analytics_db.id,
                table_name=temp_table_name,
                meta_info={
                    "type": "cross_datasource_join",
                    "left_ds_id": left_data_source_id,
                    "left_ds_name": left_ds.name,
                    "right_ds_id": right_data_source_id,
                    "right_ds_name": right_ds.name,
                    "join_type": join_type,
                    "row_count": total_rows,
                    "columns": result_df.columns.tolist(),
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )

            if total_rows <= 100:
                sample_rows = result_df.to_dict(orient="records")
                mode = "full"
            else:
                sample_rows = result_df.head(10).to_dict(orient="records")
                mode = "sample"

            return ToolResult.success(
                {
                    "status": "success",
                    "mode": mode,
                    "temp_table_name": temp_table_name,
                    "analytics_db_id": analytics_db.id,
                    "row_count": total_rows,
                    "columns": result_df.columns.tolist(),
                    "sample_rows": sample_rows,
                    "message": (
                        f"✅ Cross-datasource join completed: {total_rows} rows.\n"
                        f"Result in workspace temp table '{temp_table_name}'.\n\n"
                        f"**Next steps:**\n"
                        f"1. Query: run_sql_query_on_datasource({analytics_db.id}, 'SELECT ... FROM {temp_table_name}')\n"
                        f"2. Aggregate for visualization\n"
                        f"3. Table auto-expires in 24 hours"
                    ),
                }
            )

    except Exception as e:
        logger.error(f"Error in cross-datasource join: {e}", exc_info=True)
        return ToolResult.error_result(
            code="WORKSPACE_JOIN_CROSS_DATASOURCE_FAILED",
            message=str(e),
        )


@tool
async def list_temp_tables(config: RunnableConfig = None) -> ToolResult:
    """List all temporary tables for current session.

    Temporary tables are created by:
    - join_cross_datasource()
    - create_materialized_view()

    Returns:
        JSON list of temp tables with metadata
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id
    thread_id = runtime.thread_id

    try:
        async with app_db_session() as session:
            temp_tables = await list_temp_tables_for_thread(tenant_id, thread_id, session)

        if not temp_tables:
            return ToolResult.success(
                {
                    "temp_tables": [],
                    "count": 0,
                    "message": "No temporary tables found for this session.",
                }
            )

        temp_tables.sort(key=lambda x: x.get("created_timestamp", 0), reverse=True)

        return ToolResult.success(
            {
                "temp_tables": temp_tables,
                "count": len(temp_tables),
                "message": (
                    f"Found {len(temp_tables)} temporary table(s) in workspace. Tables auto-expire in 24 hours."
                ),
            }
        )

    except Exception as e:
        logger.error(f"Error listing temp tables: {e}", exc_info=True)
        return ToolResult.error_result(
            code="WORKSPACE_LIST_TEMP_TABLES_FAILED",
            message=str(e),
        )


@tool
async def cleanup_temp_tables(config: RunnableConfig = None) -> ToolResult:
    """Manually cleanup all temporary tables for current session.

    Use when:
    - Analysis is complete
    - Want to free up space

    Note: Temp tables auto-expire after 24 hours anyway.

    Returns:
        JSON with cleanup summary
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id
    thread_id = runtime.thread_id

    try:
        async with app_db_session() as session:
            dropped_count = await cleanup_temp_tables_for_thread(tenant_id, thread_id, session)

        message = (
            "No temporary tables to clean up."
            if dropped_count == 0
            else f"✅ Cleaned up {dropped_count} temporary table(s)."
        )

        return ToolResult.success({"status": "success", "dropped_count": dropped_count, "message": message})

    except Exception as e:
        logger.error(f"Error cleaning up temp tables: {e}", exc_info=True)
        return ToolResult.error_result(
            code="WORKSPACE_CLEANUP_TEMP_TABLES_FAILED",
            message=str(e),
        )
