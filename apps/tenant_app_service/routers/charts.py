"""Chart API routes."""

import json
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.dashboard.schemas import ChartFromSQLRequest, ChartFromSQLResponse
from apps.shared.data_source import AssetMetadataRepository, DataSourceRepository, DataSourceService
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.schemas.user import UserDTO
from apps.shared.utils.logger import get_logger
from apps.tenant_app_service.agents.tools.chart import render_chart

logger = get_logger(__name__)

router = APIRouter(prefix="/charts", tags=["charts"])

MAX_CHART_QUERY_ROWS = 500
CHART_MARKDOWN_URL_PATTERN = re.compile(r"\]\(([^)]+)\)")


@router.post("/from-sql", response_model=ChartFromSQLResponse, status_code=status.HTTP_201_CREATED)
async def create_chart_from_sql_api(
    payload: ChartFromSQLRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.DASHBOARDS_SQL_EXECUTE)),
):
    """Create a chart from SQL query results and return markdown/url for rendering."""
    try:
        service = DataSourceService(
            tenant_id=current_user.tenant_id,
            data_source_repo=DataSourceRepository(db),
            asset_repo=AssetMetadataRepository(db),
        )

        df = await service.query_data_for_actor(
            data_source_id=payload.data_source_id,
            actor=ActorContext(
                tenant_id=current_user.tenant_id,
                user_id=current_user.id,
                user_role=current_user.role,
            ),
            sql_query=payload.sql_query,
            max_rows=MAX_CHART_QUERY_ROWS,
        )

        if df.empty:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Query returned no data")

        data_list = df.to_dict(orient="records")
        chart_markdown = render_chart(
            chart_type=payload.chart_type,
            data=json.dumps(data_list, ensure_ascii=False, default=str),
            x_label=payload.x_label or payload.x_key,
            y_label=payload.y_label or payload.y_key,
            title=payload.title,
            x_key=payload.x_key,
            y_key=payload.y_key,
            theme=payload.theme,
            series_keys=payload.series_keys,
            z_key=payload.z_key,
        )

        chart_url = None
        url_match = CHART_MARKDOWN_URL_PATTERN.search(chart_markdown)
        if url_match:
            chart_url = url_match.group(1)

        return ChartFromSQLResponse(
            dataSourceId=payload.data_source_id,
            rowCount=len(df),
            chartMarkdown=chart_markdown,
            chartUrl=chart_url,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create chart from SQL: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Chart generation failed: {e}")
