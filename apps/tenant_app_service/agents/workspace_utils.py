"""Workspace utilities for cross-datasource analysis using tenant's managed database.

This module provides utilities for managing temporary tables in tenant's managed database,
which serves as a workspace for cross-datasource analysis and intermediate results.

Architecture:
- Each tenant has one managed database (SQLite/PostgreSQL) for analytics
- Temporary tables are created with naming: _temp_{thread_id}_{name}_{timestamp}
- Thread ID contains tenant_id, user_id, agent_id for isolation
- Automatic cleanup after 24 hours via background task
"""

import time
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.core.exceptions import ResourceNotFoundError
from apps.shared.data_source.adapters import db_data_source_to_domain
from apps.shared.data_source.domain import DataSourceDomain
from apps.shared.data_source.repository import DataSourceRepository
from apps.shared.db.session import app_db_session
from apps.shared.infra.analytics_db import get_db_manager_for_datasource
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

# Constants
TEMP_TABLE_PREFIX = "_temp"
TEMP_TABLE_TTL_HOURS = 24


async def get_managed_datasource(tenant_id: int, session: AsyncSession | None = None) -> DataSourceDomain:
    """Get tenant's managed database to use as workspace.

    Each tenant has a dedicated managed database (SQLite/PostgreSQL) that serves as:
    - Cross-datasource join workspace
    - Temporary table storage
    - Intermediate results cache

    Args:
        tenant_id: Tenant ID
        session: Optional async session (creates new if not provided)

    Returns:
        DataSourceDomain of tenant's managed database

    Raises:
        ResourceNotFoundError: If no managed datasource found
    """
    close_session = False
    if session is None:
        close_session = True

    async with nullcontext(session) if not close_session else app_db_session() as db:
        data_source_repo = DataSourceRepository(db)

        # Get all data sources for tenant (no type filter - supports SQLite and PostgreSQL)
        data_sources = await data_source_repo.list_by_tenant(tenant_id)
        data_sources = [db_data_source_to_domain(ds) for ds in data_sources]

        # Find first managed datasource (platform-managed database for analytics)
        managed_ds = next((ds for ds in data_sources if ds.managed), None)

        if not managed_ds:
            raise ResourceNotFoundError(
                f"No managed datasource found for tenant {tenant_id}. "
                "Each tenant requires a managed database for analytical workspace."
            )

        logger.debug(
            f"Using managed datasource '{managed_ds.name}' (ID: {managed_ds.id}, Type: {managed_ds.type}) "
            f"as workspace for tenant {tenant_id}"
        )

        return managed_ds


def generate_temp_table_name(thread_id: str, table_name: str) -> str:
    """Generate temporary table name with isolation.

    Naming convention: {prefix}_{safe_thread_id}_{table_name}_{timestamp}

    Args:
        thread_id: Thread ID (format: {tenant_id}_{user_id}_{agent_id}_{uuid})
        table_name: Business table name

    Returns:
        Full temporary table name (SQL-safe, no special chars except underscore)

    Example:
        >>> generate_temp_table_name("1_100_5_abc-def", "sales_analysis")
        "_temp_1_100_5_abc_def_sales_analysis_1703001234"
    """
    # Sanitize thread_id: replace any non-alphanumeric chars (except underscore) with underscore
    safe_thread_id = "".join(c if c.isalnum() or c == "_" else "_" for c in thread_id)

    # Sanitize table name
    safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in table_name)
    safe_name = safe_name[:30]  # Limit length

    timestamp = int(time.time())
    return f"{TEMP_TABLE_PREFIX}_{safe_thread_id}_{safe_name}_{timestamp}"


def is_temp_table(table_name: str) -> bool:
    """Check if table name is a temporary table."""
    return table_name.startswith(f"{TEMP_TABLE_PREFIX}_")


def parse_temp_table_name(table_name: str) -> dict:
    """Parse temporary table name to extract metadata.

    Args:
        table_name: Table name to parse

    Returns:
        Dictionary with parsed information:
        {
            "is_temp": bool,
            "thread_id": str (if valid),
            "tenant_id": int (if valid),
            "user_id": int (if valid),
            "agent_id": int (if valid),
            "business_name": str (if valid),
            "timestamp": int (if valid)
        }
    """
    if not is_temp_table(table_name):
        return {"is_temp": False}

    parts = table_name.split("_")
    # Format: _temp_1_100_5_sales_analysis_1703001234
    # Parts: [0]   [1][2][3][4...n-1]        [n]

    if len(parts) < 6:
        return {"is_temp": True}

    try:
        tenant_id = int(parts[1])
        user_id = int(parts[2])
        agent_id = int(parts[3])
        timestamp = int(parts[-1])
        business_name = "_".join(parts[4:-1])
        thread_id = f"{tenant_id}_{user_id}_{agent_id}"

        return {
            "is_temp": True,
            "thread_id": thread_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "business_name": business_name,
            "timestamp": timestamp,
        }
    except (ValueError, IndexError):
        return {"is_temp": True}


async def list_temp_tables_for_thread(
    tenant_id: int, thread_id: str, session: AsyncSession | None = None
) -> List[dict]:
    """List all temporary tables for specific thread.

    Args:
        tenant_id: Tenant ID
        thread_id: Thread ID
        session: Optional async session

    Returns:
        List of temp table metadata dictionaries
    """
    close_session = False
    if session is None:
        close_session = True

    async with nullcontext(session) if not close_session else app_db_session() as db:
        managed_ds = await get_managed_datasource(tenant_id, db)

        # List all tables in managed datasource
        async with get_db_manager_for_datasource(managed_ds) as db_manager:
            all_tables = await db_manager.list_tables()

        # Filter temp tables for current thread
        temp_tables = []
        for table_name in all_tables:
            parsed = parse_temp_table_name(table_name)
            if parsed.get("is_temp") and parsed.get("thread_id") == thread_id:
                # Get table row count
                try:
                    async with get_db_manager_for_datasource(managed_ds) as db_manager:
                        row_count = await db_manager.get_row_count(table_name)
                except Exception as e:
                    logger.warning(f"Failed to get row count for {table_name}: {e}")
                    row_count = 0

                temp_tables.append(
                    {
                        "table_name": table_name,
                        "business_name": parsed.get("business_name", "unknown"),
                        "row_count": row_count,
                        "created_timestamp": parsed.get("timestamp"),
                        "thread_id": thread_id,
                    }
                )

        return temp_tables


async def cleanup_temp_tables_for_thread(tenant_id: int, thread_id: str, session: AsyncSession | None = None) -> int:
    """Cleanup all temporary tables for specific thread.

    Args:
        tenant_id: Tenant ID
        thread_id: Thread ID
        session: Optional async session

    Returns:
        Number of tables dropped
    """
    close_session = False
    if session is None:
        close_session = True

    async with nullcontext(session) if not close_session else app_db_session() as db:
        temp_tables = await list_temp_tables_for_thread(tenant_id, thread_id, db)

        if not temp_tables:
            return 0

        analytics_db = await get_managed_datasource(tenant_id, db)

        dropped_count = 0
        async with get_db_manager_for_datasource(analytics_db) as db_manager:
            for temp_table in temp_tables:
                try:
                    await db_manager.drop_table(temp_table["table_name"])
                    dropped_count += 1
                    logger.info(
                        f"Dropped temp table '{temp_table['table_name']}' for tenant {tenant_id}, thread {thread_id}"
                    )
                except Exception as e:
                    logger.error(f"Failed to drop temp table '{temp_table['table_name']}': {e}")

        return dropped_count


async def register_temp_table(
    session: AsyncSession,
    tenant_id: int,
    thread_id: str,
    data_source_id: int,
    table_name: str,
    meta_info: dict,
) -> None:
    """Register temporary table metadata for tracking and cleanup.

    Args:
        session: Async database session
        tenant_id: Tenant ID
        thread_id: Thread ID
        data_source_id: Data source ID (Analytics DB)
        table_name: Temporary table name
        meta_info: Additional metadata (source info, row count, etc.)
    """
    from apps.shared.db.models import TempTableMetadata

    temp_table_meta = TempTableMetadata(
        tenant_id=tenant_id,
        thread_id=thread_id,
        data_source_id=data_source_id,
        table_name=table_name,
        meta_info=meta_info,
        row_count=meta_info.get("row_count", 0),
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=TEMP_TABLE_TTL_HOURS),
    )

    session.add(temp_table_meta)
    await session.commit()

    logger.debug(
        f"Registered temp table '{table_name}' for tenant {tenant_id}, expires in {TEMP_TABLE_TTL_HOURS} hours"
    )
