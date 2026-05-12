"""Context resource search router.

Lightweight keyword-based search across all resource types for the @mention picker.
No vector search, no FTS index — simple ILIKE matching.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.context_resource.dtos import (
    ContextResourceItemDTO,
    ContextResourceSearchResponse,
)
from apps.shared.context_resource.service import ContextResourceSearchService
from apps.shared.core.auth import get_current_user
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/context-resources", tags=["context-resources"])


def _create_service(db: AsyncSession, tenant_id: int) -> ContextResourceSearchService:
    return ContextResourceSearchService(tenant_id=tenant_id, db_session=db)


@router.get(
    "/search",
    response_model=ContextResourceSearchResponse,
    summary="Search context resources by keyword",
)
async def search_context_resources(
    query: str = Query("", min_length=0, max_length=200, description="Search keyword"),
    limit: int = Query(10, ge=1, le=50, description="Max results per resource type"),
    current_user: UserDTO = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContextResourceSearchResponse:
    """Return keyword-matched resources for the current tenant.

    Searches across documents, dashboards, reports, scheduled tasks,
    live apps, and data source assets. Results are grouped by type.

    An empty query returns recent resources (limited per type) for the
    @mention picker initial state.
    """
    service = _create_service(db, current_user.tenant_id)
    items = await service.search(query=query.strip(), limit=limit)
    return ContextResourceSearchResponse(
        items=[
            ContextResourceItemDTO(
                resource_type=item.resource_type,
                resource_id=item.resource_id,
                title=item.title,
                subtitle=item.subtitle,
            )
            for item in items
        ]
    )
