"""Artifact search for chat @mention (user-accessible, not thread-scoped)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.artifact.repository import ArtifactRepository
from apps.shared.artifact.schemas import ArtifactResponse
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.schemas.user import UserDTO

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get(
    "/context-picker",
    response_model=list[ArtifactResponse],
    summary="Search artifacts attachable via @mention in chat",
)
async def search_artifacts_for_context_picker(
    query: str = Query("", max_length=200, description="Filter by artifact title"),
    limit: int = Query(20, ge=1, le=50),
    current_user: UserDTO = Depends(require_permission(Permissions.CHAT_ACCESS)),
    db: AsyncSession = Depends(get_db),
) -> list[ArtifactResponse]:
    """Return artifacts the user may read (owner or ACL), across all threads."""
    repo = ArtifactRepository(db)
    title_query = query.strip() or None
    artifacts = await repo.list_for_user_access(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        query=title_query,
        limit=limit,
    )
    return [
        ArtifactResponse(
            type="artifact",
            artifact_type=a.artifact_type,
            id=a.id,
            resource_id=a.resource_id,
            url=a.url,
            title=a.title or "Untitled",
            metadata=a.artifact_metadata or {},
            created_at=a.created_at,
            owner_username=a.owner_user.username if a.owner_user else None,
        )
        for a in artifacts
    ]
