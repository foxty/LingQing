"""Application factories — assemble execution services with credential ports wired."""

from __future__ import annotations

from apps.shared.external_systems.api_connector.execution import ApiConnectorExecutionService
from apps.shared.external_systems.credentials.resolver import IntegrationCredentialResolver
from apps.shared.external_systems.data_source.repository import AssetMetadataRepository, DataSourceRepository
from apps.shared.external_systems.data_source.service import DataSourceService


def api_connector_execution_service(tenant_id: int, db_session) -> ApiConnectorExecutionService:
    """ApiConnectorExecutionService with BYOT auth resolution wired."""
    return ApiConnectorExecutionService(
        tenant_id=tenant_id,
        db_session=db_session,
        user_integration_auth=IntegrationCredentialResolver(db_session),
    )


def data_source_service(tenant_id: int, db_session) -> DataSourceService:
    """DataSourceService with credential resolver composed at the application boundary."""
    return DataSourceService(
        tenant_id=tenant_id,
        data_source_repo=DataSourceRepository(db_session),
        asset_repo=AssetMetadataRepository(db_session),
        credential_resolver=IntegrationCredentialResolver(db_session),
    )
