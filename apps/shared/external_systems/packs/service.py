"""Application service for listing and installing API connector packs."""

from __future__ import annotations

from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.api_connector.domain import OAuth2AuthConfig, RatePolicyDomain
from apps.shared.external_systems.api_connector.service import ApiConnectorService
from apps.shared.external_systems.packs.loader import ApiConnectorPackCatalog
from apps.shared.external_systems.packs.schemas import (
    ApiConnectorPackSummary,
    InstallApiConnectorPackRequest,
)


class ApiConnectorPackService:
    def __init__(self, tenant_id: int, db_session, catalog: ApiConnectorPackCatalog | None = None) -> None:
        self._tenant_id = tenant_id
        self._db = db_session
        self._catalog = catalog or ApiConnectorPackCatalog()
        self._connectors = ApiConnectorService(tenant_id=tenant_id, db_session=db_session)

    def list_packs(self) -> list[ApiConnectorPackSummary]:
        return [
            ApiConnectorPackSummary(
                pack_id=manifest.pack_id,
                version=manifest.version,
                name=manifest.connector.name,
                description=manifest.connector.description,
            )
            for manifest in self._catalog.list()
        ]

    async def install(self, *, actor: ActorContext, request: InstallApiConnectorPackRequest):
        manifest = self._catalog.get(request.pack_id)
        existing = await self._connectors.connector_repo.get_by_tenant_and_pack_ref(
            self._tenant_id,
            manifest.pack_ref,
        )
        if existing is not None:
            if existing.agent_instructions != manifest.agent_instructions:
                existing.agent_instructions = manifest.agent_instructions
                await self._connectors.connector_repo.update(existing)
            return await self._connectors.get_connector_for_actor(
                connector_id=existing.id,
                actor=actor,
            )

        auth_config = OAuth2AuthConfig(
            authorize_url=manifest.oauth.authorize_url,
            token_url=manifest.oauth.token_url,
            client_id=request.client_id,
            client_secret=request.client_secret,
            scopes=list(manifest.oauth.scopes),
            scope_param=manifest.oauth.scope_param,
            redirect_uri=request.redirect_uri,
            token_auth_method=manifest.oauth.token_auth_method,
            token_response_path=manifest.oauth.token_response_path,
        )
        connector = await self._connectors.create_connector(
            owner_id=actor.user_id,
            name=manifest.connector.name,
            description=manifest.connector.description,
            base_url=manifest.connector.base_url,
            auth_type=manifest.connector.auth_type,
            auth_config=auth_config,
            rate_policy=RatePolicyDomain(),
            schema_source_type="manual",
            schema_source_url=None,
            credential_mode=manifest.connector.credential_mode,
            execution_rules=manifest.execution_rules.to_domain(),
            pack_ref=manifest.pack_ref,
            agent_instructions=manifest.agent_instructions,
        )

        for operation_template in manifest.operations:
            operation = await self._connectors.add_manual_operation_for_actor(
                connector_id=connector.id,
                actor=actor,
                method=operation_template.method,
                path_template=operation_template.path,
                operation_id=operation_template.operation_id,
                summary=operation_template.summary,
                description=operation_template.description,
                tags=[manifest.pack_id],
                request_schema=operation_template.request_schema,
                response_schema=operation_template.response_schema,
            )
            if not operation_template.enabled:
                await self._connectors.update_operation_status_for_actor(
                    operation_id=operation.id,
                    actor=actor,
                    status="disabled",
                )
        return connector
