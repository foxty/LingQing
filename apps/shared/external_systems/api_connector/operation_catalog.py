"""Resource-index side effects for indexed API operations (control plane)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR
from apps.shared.external_systems.api_connector.domain import ApiOperationDomain
from apps.shared.search.schemas import ResourceIndexCreateDTO
from apps.shared.utils.logger import get_logger

logger = get_logger(__name__)


class ApiOperationResourceIndexWriter:
    """Create or remove search resource index rows for API operations."""

    def __init__(self, *, tenant_id: int, db_session: AsyncSession) -> None:
        self._tenant_id = tenant_id
        self._db_session = db_session
        self._resource_index_service = None

    async def _get_resource_index_service(self):
        if self._resource_index_service is None:
            from apps.shared.search.sync_service import ResourceIndexService

            self._resource_index_service = await ResourceIndexService.create(
                tenant_id=self._tenant_id,
                db_session=self._db_session,
            )
        return self._resource_index_service

    async def create_for_operation(self, operation: ApiOperationDomain) -> None:
        try:
            async with self._db_session.begin_nested():
                searchable_text = operation.to_searchable_text()
                resource_index_svc = await self._get_resource_index_service()
                raw_content = {"text": searchable_text, "meta": {}}

            await resource_index_svc.create_or_update(
                ResourceIndexCreateDTO(
                    tenant_id=self._tenant_id,
                    resource_type=RESOURCE_TYPE_API_CONNECTOR,
                    resource_id=operation.id,
                    owner_id=operation.owner_id,
                    raw_content=raw_content,
                    content_updated_at=operation.updated_at,
                    parent_id=operation.connector_id,
                )
            )
        except Exception as exc:
            logger.warning("Failed to create resource index for api operation %d: %s", operation.id, exc)

    async def remove_for_operation(self, operation: ApiOperationDomain) -> None:
        await self.remove_for_operation_ids([operation.id])

    async def remove_for_operation_ids(self, operation_ids: list[int]) -> None:
        if not operation_ids:
            return
        try:
            resource_index_svc = await self._get_resource_index_service()
            await resource_index_svc.delete_many(RESOURCE_TYPE_API_CONNECTOR, operation_ids)
        except Exception as exc:
            logger.warning(
                "Failed to delete resource indexes for %s api operations: %s",
                len(operation_ids),
                exc,
            )

    async def refresh_for_operation(self, operation: ApiOperationDomain) -> None:
        from apps.shared.external_systems.api_connector.constants import OPERATION_STATUS_ACTIVE

        if operation.status == OPERATION_STATUS_ACTIVE:
            await self.create_for_operation(operation)
        else:
            await self.remove_for_operation(operation)