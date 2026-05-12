"""API connector management and invocation routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.api_connector.adapters import auth_config_to_dict, operation_domain_to_response
from apps.shared.api_connector.domain import OperationStatus
from apps.shared.api_connector.execution import ApiConnectorExecutionService
from apps.shared.api_connector.schemas import (
    ApiConnectorCreateRequest,
    ApiConnectorResponse,
    ApiConnectorUpdateRequest,
    ApiOperationCallRequest,
    ApiOperationCallResponse,
    ApiOperationCreateRequest,
    ApiOperationResponse,
    ApiOperationSearchResponse,
    ApiOperationStatsResponse,
    ApiOperationStatusUpdateRequest,
    ApiOperationUpdateRequest,
    SyncSchemaRequest,
    SyncSchemaResponse,
)
from apps.shared.api_connector.service import ApiConnectorService
from apps.shared.authz.ta_permissions import TenantAppPermissions as Permissions
from apps.shared.core.auth import require_permission
from apps.shared.db.session import get_db
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR
from apps.shared.schemas.pagination import PaginatedResponse
from apps.shared.schemas.user import UserDTO
from apps.shared.tag.adapters import domain_tag_value_to_api
from apps.shared.tag.schemas import TagBindingCreateRequest, TagValueDTO
from apps.shared.tag.service import TagService
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api-connectors", tags=["api-connectors"])


async def _service(db: AsyncSession, tenant_id: int) -> ApiConnectorService:
    return ApiConnectorService(tenant_id=tenant_id, db_session=db)


def _create_tag_service(db: AsyncSession, tenant_id: int) -> TagService:
    return TagService.create(tenant_id, db)


def _actor_ctx(current_user: UserDTO) -> ActorContext:
    return ActorContext(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


@router.post("", response_model=ApiConnectorResponse, status_code=status.HTTP_201_CREATED)
async def create_connector(
    payload: ApiConnectorCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.API_CONNECTORS_CREATE)),
):
    service = await _service(db, current_user.tenant_id)
    return await service.create_connector(
        owner_id=current_user.id,
        name=payload.name,
        description=payload.description,
        base_url=payload.base_url,
        auth_type=payload.auth_type,
        auth_config=auth_config_to_dict(payload.auth_config),
        rate_policy=payload.rate_policy.to_domain(),
        schema_source_type=payload.schema_source_type,
        schema_source_url=payload.schema_source_url,
    )


@router.get("", response_model=list[ApiConnectorResponse])
async def list_connectors(
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    return await service.list_connectors_for_actor(actor=_actor_ctx(current_user))


@router.get("/{connector_id}", response_model=ApiConnectorResponse)
async def get_connector(
    connector_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    return await service.get_connector_for_actor(
        connector_id=connector_id,
        actor=_actor_ctx(current_user),
    )


@router.patch("/{connector_id}", response_model=ApiConnectorResponse)
async def update_connector(
    connector_id: int,
    payload: ApiConnectorUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    update_fields = payload.model_dump(exclude_unset=True, exclude={"rate_policy"})
    if payload.rate_policy is not None:
        update_fields["rate_policy"] = payload.rate_policy.to_domain()

    return await service.update_connector_for_actor(
        connector_id=connector_id,
        actor=_actor_ctx(current_user),
        **update_fields,
    )


@router.delete("/{connector_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connector(
    connector_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    await service.delete_connector_for_actor(connector_id=connector_id, actor=_actor_ctx(current_user))


@router.post("/{connector_id}/sync-schema", response_model=SyncSchemaResponse)
async def sync_schema(
    connector_id: int,
    payload: SyncSchemaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    summary = await service.sync_operations_from_schema_for_actor(
        connector_id=connector_id,
        actor=_actor_ctx(current_user),
        file_content=payload.file_content,
    )
    return SyncSchemaResponse(
        operations_created=summary.added,
        added=summary.added,
        updated=summary.updated,
        staled=summary.staled,
        unchanged=summary.unchanged,
    )


@router.post("/{connector_id}/operations", response_model=ApiOperationResponse, status_code=status.HTTP_201_CREATED)
async def add_manual_operation(
    connector_id: int,
    payload: ApiOperationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    row = await service.add_manual_operation_for_actor(
        connector_id=connector_id,
        actor=_actor_ctx(current_user),
        method=payload.method,
        path_template=payload.path_template,
        operation_id=payload.operation_id,
        summary=payload.summary,
        description=payload.description,
        tags=payload.tags,
        request_schema=payload.request_schema,
        response_schema=payload.response_schema,
        auth_requirement=payload.auth_requirement,
        risk_level=payload.risk_level,
    )
    return operation_domain_to_response(row)


@router.patch("/operations/{operation_id}/status", response_model=ApiOperationResponse)
async def update_operation_status(
    operation_id: int,
    payload: ApiOperationStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    row = await service.update_operation_status_for_actor(
        operation_id=operation_id,
        actor=_actor_ctx(current_user),
        status=payload.status,
    )
    return operation_domain_to_response(row)


@router.patch("/operations/{operation_id}", response_model=ApiOperationResponse)
async def update_operation(
    operation_id: int,
    payload: ApiOperationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    row = await service.update_operation_for_actor(
        operation_id=operation_id,
        actor=_actor_ctx(current_user),
        method=payload.method,
        path_template=payload.path_template,
        operation_id_new=payload.operation_id,
        summary=payload.summary,
        description=payload.description,
        tags=payload.tags,
        request_schema=payload.request_schema,
        response_schema=payload.response_schema,
        auth_requirement=payload.auth_requirement,
        risk_level=payload.risk_level,
    )
    return operation_domain_to_response(row)


@router.delete("/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_operation(
    operation_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    await service.delete_operation_for_actor(
        operation_id=operation_id,
        actor=_actor_ctx(current_user),
    )


@router.get("/{connector_id}/operations", response_model=PaginatedResponse[ApiOperationResponse])
async def list_operations(
    connector_id: int,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    query: str | None = Query(None, min_length=1, description="Search query"),
    status: OperationStatus | None = Query(None, description="Filter by status: active/disabled/stale"),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    rows, pagination = await service.list_operations_for_actor(
        connector_id=connector_id,
        actor=_actor_ctx(current_user),
        page=page,
        page_size=page_size,
        status=status,
        query=query,
    )
    return PaginatedResponse(
        items=[operation_domain_to_response(row) for row in rows],
        total=pagination.total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=pagination.total_pages,
    )


@router.get("/{connector_id}/operations/stats", response_model=ApiOperationStatsResponse)
async def get_operation_stats(
    connector_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    return await service.get_operation_stats_for_actor(
        connector_id=connector_id,
        actor=_actor_ctx(current_user),
    )


@router.get("/operations/search", response_model=ApiOperationSearchResponse)
async def search_operations(
    q: str | None = Query(default=None),
    connector_id: int | None = Query(default=None),
    status: OperationStatus | None = Query(default="active"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    rows, pagination = await service.search_operations_for_actor(
        query=q,
        connector_id=connector_id,
        status=status,
        page=page,
        page_size=page_size,
        actor=_actor_ctx(current_user),
    )
    items = [operation_domain_to_response(row) for row in rows]
    return ApiOperationSearchResponse(
        items=items,
        total=pagination.total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=pagination.total_pages,
    )


@router.post("/operations/{operation_uid}/call", response_model=ApiOperationCallResponse)
async def call_operation(
    operation_uid: str,
    payload: ApiOperationCallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    exec_service = ApiConnectorExecutionService(tenant_id=current_user.tenant_id, db_session=db)
    result = await exec_service.execute_operation_for_actor(
        operation_uid=operation_uid,
        actor=_actor_ctx(current_user),
        parameters=payload.parameters,
    )
    return ApiOperationCallResponse(
        status_code=result.status_code,
        body=result.body,
        headers=result.headers,
        elapsed_ms=result.elapsed_ms,
        error=result.error,
    )


@router.get("/{connector_id}/tags", response_model=list[TagValueDTO], include_in_schema=False)
async def list_connector_tags(
    connector_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(
        require_permission([Permissions.API_CONNECTORS_CREATE, Permissions.API_CONNECTORS_MANAGE])
    ),
):
    service = await _service(db, current_user.tenant_id)
    await service.get_connector_for_actor(connector_id=connector_id, actor=_actor_ctx(current_user))
    tag_service = _create_tag_service(db, current_user.tenant_id)
    tag_values = await tag_service.list_tags_for_resource(RESOURCE_TYPE_API_CONNECTOR, connector_id)
    return [domain_tag_value_to_api(tv) for tv in tag_values]


@router.post("/{connector_id}/tags", response_model=TagValueDTO, include_in_schema=False)
async def bind_connector_tag(
    connector_id: int,
    payload: TagBindingCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
):
    service = await _service(db, current_user.tenant_id)
    await service.get_connector_for_actor(connector_id=connector_id, actor=_actor_ctx(current_user))
    tag_service = _create_tag_service(db, current_user.tenant_id)
    tag_value = await tag_service.bind_tag_value(
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=connector_id,
        tag_value_id=payload.tag_value_id,
        created_by=current_user.id,
    )
    return domain_tag_value_to_api(tag_value)


@router.delete("/{connector_id}/tags/{tag_value_id}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def unbind_connector_tag(
    connector_id: int,
    tag_value_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserDTO = Depends(require_permission(Permissions.TAGS_MANAGE)),
):
    service = await _service(db, current_user.tenant_id)
    await service.get_connector_for_actor(connector_id=connector_id, actor=_actor_ctx(current_user))
    tag_service = _create_tag_service(db, current_user.tenant_id)
    await tag_service.unbind_tag_value(
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=connector_id,
        tag_value_id=tag_value_id,
    )
