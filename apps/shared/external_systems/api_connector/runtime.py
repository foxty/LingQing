"""Data-plane bridge: load committed connector + operation state for execution."""

from __future__ import annotations

from dataclasses import dataclass

from apps.shared.authz.authz_query_builder import evaluate_resource_action
from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.domain.actor import ActorContext
from apps.shared.domain.types import ABAC_ACTION_READ, RESOURCE_TYPE_API_CONNECTOR
from apps.shared.external_systems.api_connector.adapters import connector_domain_with_resolved_auth
from apps.shared.external_systems.api_connector.domain import ApiConnectorDomain, ApiOperationDomain
from apps.shared.external_systems.api_connector.repository import ApiConnectorRepository
from apps.shared.external_systems.credentials.resolver import IntegrationCredentialResolver
from apps.shared.external_systems.domain.ports import UserIntegrationAuthPort
from apps.shared.external_systems.domain.types import IntegrationPurpose


@dataclass(frozen=True)
class ApiConnectorExecutionContext:
    """Resolved snapshot used for a single HTTP execution."""

    operation_domain: ApiOperationDomain
    connector_domain: ApiConnectorDomain
    connector_id: int
    connector_owner_id: int


async def load_api_connector_execution_context(
    *,
    tenant_id: int,
    db_session,
    actor: ActorContext,
    operation: ApiOperationDomain,
    user_integration_auth: UserIntegrationAuthPort | None = None,
) -> ApiConnectorExecutionContext:
    try:
        operation.assert_runnable_for_execution()
    except ValidationError as exc:
        raise ResourceNotFoundError(
            f"Api operation not runnable: {operation.operation_uid or operation.id} ({exc})"
        ) from exc

    connector_repo = ApiConnectorRepository(db_session)
    execution_load = await connector_repo.get_execution_load(operation.connector_id, tenant_id)
    if execution_load is None:
        raise ResourceNotFoundError(f"Api connector not found: {operation.connector_id}")

    allowed = await evaluate_resource_action(
        db_session=db_session,
        tenant_id=tenant_id,
        user_id=actor.user_id,
        user_role=actor.user_role,
        resource_type=RESOURCE_TYPE_API_CONNECTOR,
        resource_id=execution_load.credential_subject.id,
        resource_owner_id=execution_load.connector.owner_id,
        action=ABAC_ACTION_READ,
    )
    if not allowed:
        raise ResourceNotFoundError(f"Access denied to API connector: {execution_load.credential_subject.id}")

    auth_port = user_integration_auth or IntegrationCredentialResolver(db_session)
    auth_dict = await auth_port.resolve_api_connector_auth_config(
        connector=execution_load.credential_subject,
        actor=actor,
        purpose=IntegrationPurpose.EXECUTE,
    )
    connector_domain = connector_domain_with_resolved_auth(execution_load.connector, auth_dict)
    try:
        connector_domain.assert_runnable_for_execution()
    except ValidationError as exc:
        raise ResourceNotFoundError(f"Api connector not runnable: {operation.connector_id} ({exc})") from exc

    return ApiConnectorExecutionContext(
        operation_domain=operation,
        connector_domain=connector_domain,
        connector_id=execution_load.credential_subject.id,
        connector_owner_id=execution_load.connector.owner_id,
    )