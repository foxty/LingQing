"""Database query tools for tenant-specific data sources.

Provides SQL query execution capabilities with:
- Consistent JSON response format
- Hard row limit enforcement for predictable behavior
- Clear error messages for query optimization
"""

import pandas as pd
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.shared.core.exceptions import AuthorizationError, ResourceNotFoundError, ValidationError
from apps.shared.data_source import DataSourceService
from apps.shared.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.db.session import app_db_session
from apps.shared.domain.actor import ActorContext
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.context import delegated_data_source_ids, extract_runtime_context
from apps.tenant_app_service.agents.tools.tool_result import ToolResult

logger = get_logger(__name__)

# Result handling constants
MAX_QUERY_RESULT_ROWS = 200  # Hard limit for query results
MAX_CELL_LENGTH = 200  # Truncate long text cells for readability
MAX_SEARCH_PAGE = 5
ASSET_PAGE_SIZE = 10


# ========== Helper Functions ==========


def _format_response(df: pd.DataFrame, data_source_id: int) -> dict:
    """Format query response with truncated long text cells."""
    result_data = df.to_dict(orient="records")

    # Truncate long text values for readability
    for row in result_data:
        for key, value in row.items():
            if isinstance(value, str) and len(value) > MAX_CELL_LENGTH:
                row[key] = value[:MAX_CELL_LENGTH] + "...[truncated]"

    return {
        "data_source_id": data_source_id,
        "row_count": len(df),
        "columns": df.columns.tolist(),
        "rows": result_data,
    }


# ========== Tools ==========


@tool
async def list_data_sources(config: RunnableConfig) -> ToolResult:
    """List all data sources with SQL dialect hints. Managed by admin.

    Args:
        config: Runtime config

    Returns:
        JSON list with data_source_id, name, type, managed, description
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id
    tenant_name = runtime.user.tenant_name
    actor = ActorContext(
        tenant_id=tenant_id,
        user_id=runtime.user.user_id,
        user_role=runtime.user.role,
    )

    logger.info(f"Listing data sources for tenant {tenant_name} (ID: {tenant_id})")

    try:
        async with app_db_session() as session:
            service = DataSourceService(
                tenant_id=tenant_id,
                data_source_repo=DataSourceRepository(session),
                asset_repo=AssetMetadataRepository(session),
            )
            data_sources = await service.list_data_sources_for_actor(actor=actor)
            profile = runtime.capability_profile
            attached_ids = delegated_data_source_ids(profile) or []
            by_id = {ds.id: ds for ds in data_sources}
            for ds_id in attached_ids:
                if ds_id in by_id:
                    continue
                try:
                    extra = await service.require_read_access_for_actor(
                        data_source_id=ds_id,
                        actor=actor,
                        delegated_ids=attached_ids,
                    )
                except (AuthorizationError, ResourceNotFoundError):
                    continue
                by_id[ds_id] = extra
            allowed = profile.allowed_data_source_ids if profile else None
            visible = list(by_id.values())
            if allowed is not None:
                allowed_set = set(allowed)
                visible = [ds for ds in visible if ds.id in allowed_set]

            response = []
            for ds in visible:
                response.append(
                    {
                        "data_source_id": ds.id,
                        "name": ds.name,
                        "type": ds.type,
                        "managed": ds.managed,
                        "description": ds.to_llm_text(),
                    }
                )

            logger.info(f"Found {len(response)} data sources for tenant {tenant_name}")
            return ToolResult.success(response)

    except Exception as e:
        error_msg = f"Error listing data sources: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return ToolResult.error_result(error_msg, code="LIST_DATA_SOURCES_FAILED")


@tool
async def run_sql_query_on_datasource(
    data_source_id: int,
    sql_query: str,
    config: RunnableConfig,
) -> ToolResult:
    """Execute SELECT query on data source. Max {MAX_QUERY_RESULT_ROWS} rows. Use LIMIT/WHERE/GROUP BY to control size.

    Args:
        data_source_id: Data source ID
        sql_query: SQL SELECT query
        config: Runtime config

    Returns:
        JSON with data_source_id, row_count, columns[], rows[] or error
    """
    runtime = extract_runtime_context(config)
    tenant_id = runtime.user.tenant_id
    user_id = runtime.user.user_id
    user_role = runtime.user.role

    logger.info(f"Executing SQL query on data source {data_source_id}: {sql_query[:100]}...")
    profile = runtime.capability_profile
    if (
        profile
        and profile.allowed_data_source_ids is not None
        and data_source_id not in profile.allowed_data_source_ids
    ):
        return ToolResult.error_result("Data source is not assigned to this agent", code="PERMISSION_DENIED")

    try:
        async with app_db_session() as session:
            service = DataSourceService(
                tenant_id=tenant_id,
                data_source_repo=DataSourceRepository(session),
                asset_repo=AssetMetadataRepository(session),
            )

            df = await service.query_data_for_actor(
                data_source_id=data_source_id,
                sql_query=sql_query,
                actor=ActorContext(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    user_role=user_role,
                ),
                max_rows=MAX_QUERY_RESULT_ROWS,
                delegated_ids=delegated_data_source_ids(profile),
            )
            logger.info(f"Query returned {len(df)} rows")

            payload = _format_response(df, data_source_id)
            return ToolResult.success(payload)

    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return ToolResult.error_result(str(e), code="INVALID_PARAM")
    except (ValidationError, AuthorizationError) as e:
        logger.warning(f"Query blocked: {e}")
        return ToolResult.error_result(str(e), code="UNAUTHORIZED_OR_VALIDATION")
    except Exception as e:
        error_msg = f"Error executing SQL query: {str(e)}"
        logger.exception(error_msg)
        return ToolResult.error_result(error_msg, code="SQL_EXECUTION_ERROR", retryable=True)
