"""Shared pack install/sync helpers for ``ApiConnectorService`` (same session layer)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from apps.shared.core.exceptions import ResourceNotFoundError, ValidationError
from apps.shared.domain.actor import ActorContext
from apps.shared.external_systems.api_connector.constants import (
    AUTH_REQUIREMENT_REQUIRED,
    OPERATION_STATUS_ACTIVE,
    OPERATION_STATUS_DISABLED,
    OPERATION_STATUS_STALE,
)
from apps.shared.external_systems.api_connector.domain import (
    ApiConnectorDomain,
    ApiOperationDomain,
    OAuth2AuthConfig,
    RatePolicyDomain,
)
from apps.shared.external_systems.api_connector.schemas import (
    ApiConnectorResponse,
    InstallPackOAuthInput,
    PackSyncSummaryDTO,
)
from apps.shared.external_systems.packs.catalog import IntegrationPackCatalog
from apps.shared.external_systems.packs.schemas import ApiConnectorPackManifest, PackOperationSchema
from apps.shared.external_systems.packs.versioning import pack_id_from_ref


class ApiConnectorPackSessionPort(Protocol):
    async def get_connector_by_pack_ref(self, pack_ref: str) -> ApiConnectorDomain | None: ...
    async def create_connector(self, **kwargs: Any) -> ApiConnectorResponse: ...
    async def get_connector_domain(self, connector_id: int) -> ApiConnectorDomain | None: ...
    async def require_write_access_for_actor(self, actor: ActorContext, connector: ApiConnectorDomain) -> None: ...
    async def sync_pack_oauth_scopes(self, connector_id: int, manifest_scopes: list[str]) -> tuple[bool, bool]: ...
    async def save_connector_pack_metadata(self, connector: ApiConnectorDomain) -> None: ...
    async def list_operation_domains_for_connector(self, connector_id: int) -> list[ApiOperationDomain]: ...
    async def create_operation_domain(self, operation: ApiOperationDomain) -> ApiOperationDomain: ...
    async def update_operation_domain(self, operation: ApiOperationDomain) -> None: ...
    async def refresh_operation_resource_index(self, operation: ApiOperationDomain) -> None: ...
    async def remove_operation_resource_index(self, operation: ApiOperationDomain) -> None: ...
    async def get_connector_for_actor(self, *, connector_id: int, actor: ActorContext) -> ApiConnectorResponse: ...


@dataclass(frozen=True)
class PackOperationSyncSpec:
    """Normalized operation shape used for content hashing during pack sync."""

    method: str
    path_template: str
    operation_id: str
    summary: str
    description: str | None
    request_schema: dict[str, Any]
    response_schema: dict[str, Any]
    enabled: bool
    pack_id: str

    @classmethod
    def from_template(cls, template: PackOperationSchema, *, pack_id: str) -> PackOperationSyncSpec:
        return cls(
            method=template.method.upper(),
            path_template=template.path,
            operation_id=template.operation_id,
            summary=template.summary,
            description=template.description,
            request_schema=template.request_schema,
            response_schema=template.response_schema,
            enabled=template.enabled,
            pack_id=pack_id,
        )

    @property
    def target_status(self) -> str:
        return OPERATION_STATUS_ACTIVE if self.enabled else OPERATION_STATUS_DISABLED

    def content_hash(self) -> str:
        return ApiOperationDomain.compute_content_hash(
            method=self.method,
            path_template=self.path_template,
            operation_id=self.operation_id,
            summary=self.summary,
            description=self.description,
            tags=[self.pack_id],
            request_schema=self.request_schema,
            response_schema=self.response_schema,
            auth_requirement=AUTH_REQUIREMENT_REQUIRED,
        )

    @property
    def operation_uid_seed(self) -> str:
        return f"{self.method}:{self.path_template}:{self.operation_id}"


@dataclass
class _PackSyncCounters:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    staled: int = 0


async def install_integration_pack(
    session: ApiConnectorPackSessionPort,
    *,
    actor: ActorContext,
    manifest: ApiConnectorPackManifest,
    oauth: InstallPackOAuthInput,
) -> tuple[ApiConnectorResponse, PackSyncSummaryDTO]:
    existing = await session.get_connector_by_pack_ref(manifest.pack_ref)
    if existing is not None:
        return await apply_pack_manifest(
            session,
            connector_id=existing.id,
            actor=actor,
            manifest=manifest,
        )

    client_id = (oauth.client_id or "").strip()
    client_secret = (oauth.client_secret or "").strip()
    if not client_id or not client_secret:
        raise ValidationError("OAuth client_id and client_secret are required for a new pack install")

    auth_config = OAuth2AuthConfig(
        authorize_url=manifest.oauth.authorize_url,
        token_url=manifest.oauth.token_url,
        client_id=client_id,
        client_secret=client_secret,
        scopes=list(manifest.oauth.scopes),
        scope_param=manifest.oauth.scope_param,
        redirect_uri=oauth.redirect_uri,
        token_auth_method=manifest.oauth.token_auth_method,
        token_response_path=manifest.oauth.token_response_path,
    )
    created = await session.create_connector(
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
        installed_pack_version=None,
        agent_instructions=None,
    )
    return await apply_pack_manifest(session, connector_id=created.id, actor=actor, manifest=manifest)


async def sync_installed_pack_for_connector(
    session: ApiConnectorPackSessionPort,
    *,
    actor: ActorContext,
    connector_id: int,
    catalog: IntegrationPackCatalog[ApiConnectorPackManifest],
) -> tuple[ApiConnectorResponse, PackSyncSummaryDTO]:
    connector = await session.get_connector_domain(connector_id)
    if connector is None:
        raise ResourceNotFoundError(f"Api connector not found: {connector_id}")
    if not connector.pack_ref:
        raise ValidationError("Connector is not backed by an integration pack")
    pack_id = pack_id_from_ref(connector.pack_ref)
    if not pack_id:
        raise ValidationError("Connector has an invalid pack_ref")
    manifest = catalog.get(pack_id)
    if manifest.pack_ref != connector.pack_ref:
        raise ValidationError(
            f"Installed pack major version {connector.pack_ref!r} does not match catalog {manifest.pack_ref!r}"
        )
    return await apply_pack_manifest(session, connector_id=connector_id, actor=actor, manifest=manifest)


async def apply_pack_manifest(
    session: ApiConnectorPackSessionPort,
    *,
    connector_id: int,
    actor: ActorContext,
    manifest: ApiConnectorPackManifest,
) -> tuple[ApiConnectorResponse, PackSyncSummaryDTO]:
    connector = await _load_and_validate_pack_connector(session, connector_id, manifest)
    await session.require_write_access_for_actor(actor, connector)

    specs = [PackOperationSyncSpec.from_template(template, pack_id=manifest.pack_id) for template in manifest.operations]
    counters = await _sync_pack_operations(session, connector, specs, manifest.pack_id)
    counters.staled = await _stale_removed_pack_operations(
        session,
        connector_id=connector.id,
        pack_id=manifest.pack_id,
        manifest_operation_ids={spec.operation_id for spec in specs},
    )
    scopes_changed, scopes_expanded = await session.sync_pack_oauth_scopes(
        connector.id,
        list(manifest.oauth.scopes),
    )
    connector.apply_pack_manifest_metadata(
        agent_instructions=manifest.agent_instructions,
        execution_rules=manifest.execution_rules.to_domain(),
        installed_pack_version=manifest.version,
        updated_at=datetime.now(UTC),
    )
    await session.save_connector_pack_metadata(connector)

    summary = PackSyncSummaryDTO(
        added=counters.added,
        updated=counters.updated,
        staled=counters.staled,
        unchanged=counters.unchanged,
        installed_pack_version=manifest.version,
        catalog_version=manifest.version,
        scopes_changed=scopes_changed,
        scopes_expanded=scopes_expanded,
    )
    response = await session.get_connector_for_actor(connector_id=connector_id, actor=actor)
    return response, summary


async def _load_and_validate_pack_connector(
    session: ApiConnectorPackSessionPort,
    connector_id: int,
    manifest: ApiConnectorPackManifest,
) -> ApiConnectorDomain:
    connector = await session.get_connector_domain(connector_id)
    if not connector:
        raise ResourceNotFoundError(f"Api connector not found: {connector_id}")
    if not connector.pack_ref:
        raise ValidationError("Connector is not backed by an integration pack")
    if connector.pack_ref != manifest.pack_ref:
        raise ValidationError(
            f"Pack major ref mismatch: connector has {connector.pack_ref!r}, manifest has {manifest.pack_ref!r}"
        )
    return connector


async def _sync_pack_operations(
    session: ApiConnectorPackSessionPort,
    connector: ApiConnectorDomain,
    specs: list[PackOperationSyncSpec],
    pack_id: str,
) -> _PackSyncCounters:
    counters = _PackSyncCounters()
    all_operations = await session.list_operation_domains_for_connector(connector.id)
    pack_managed = [op for op in all_operations if op.is_pack_managed(pack_id)]
    by_operation_id = {op.operation_id: op for op in pack_managed if op.operation_id}

    for spec in specs:
        changed = await _upsert_pack_operation(session, connector, spec, by_operation_id.get(spec.operation_id))
        if changed == "added":
            counters.added += 1
        elif changed == "updated":
            counters.updated += 1
        else:
            counters.unchanged += 1
    return counters


async def _upsert_pack_operation(
    session: ApiConnectorPackSessionPort,
    connector: ApiConnectorDomain,
    spec: PackOperationSyncSpec,
    current: ApiOperationDomain | None,
) -> str:
    content_hash = spec.content_hash()

    if current is None:
        created = ApiOperationDomain.draft_pack_managed(
            connector_id=connector.id,
            owner_id=connector.owner_id,
            pack_id=spec.pack_id,
            method=spec.method,
            path_template=spec.path_template,
            operation_id=spec.operation_id,
            summary=spec.summary,
            description=spec.description,
            request_schema=spec.request_schema,
            response_schema=spec.response_schema,
            target_status=spec.target_status,
            operation_uid_seed=spec.operation_uid_seed,
        )
        saved = await session.create_operation_domain(created)
        await session.refresh_operation_resource_index(saved)
        return "added"

    should_update = (
        current.content_hash != content_hash
        or current.status != spec.target_status
        or not current.upstream_key
    )
    if not should_update:
        return "unchanged"

    tags = current.tags
    if spec.pack_id not in tags:
        tags = [*tags, spec.pack_id]
    next_status = current.status
    if current.status != OPERATION_STATUS_DISABLED:
        next_status = spec.target_status
    updated = replace(
        current,
        method=spec.method,
        path_template=spec.path_template,
        summary=spec.summary,
        description=spec.description,
        tags=tags,
        request_schema=spec.request_schema,
        response_schema=spec.response_schema,
        upstream_key=ApiOperationDomain.build_pack_upstream_key(spec.operation_id),
        content_hash=content_hash,
        status=next_status,
        updated_at=datetime.now(UTC),
    )
    await session.update_operation_domain(updated)
    await session.refresh_operation_resource_index(updated)
    return "updated"


async def _stale_removed_pack_operations(
    session: ApiConnectorPackSessionPort,
    *,
    connector_id: int,
    pack_id: str,
    manifest_operation_ids: set[str],
) -> int:
    all_operations = await session.list_operation_domains_for_connector(connector_id)
    pack_managed = [op for op in all_operations if op.is_pack_managed(pack_id)]
    staled = 0
    for operation in pack_managed:
        if not operation.operation_id or operation.operation_id in manifest_operation_ids:
            continue
        if operation.status == OPERATION_STATUS_STALE:
            continue
        stale_op = operation.marked_stale(at=datetime.now(UTC))
        await session.update_operation_domain(stale_op)
        await session.remove_operation_resource_index(stale_op)
        staled += 1
    return staled