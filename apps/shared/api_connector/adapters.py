"""Mapping adapters for API connector layers."""

from __future__ import annotations

import dataclasses
from typing import Any

from pydantic import BaseModel

from apps.shared.api_connector.domain import (
    ApiConnectorDomain,
    ApiKeyAuthConfig,
    ApiOperationDomain,
    BasicAuthConfig,
    BearerAuthConfig,
    CustomAuthConfig,
    NoAuthConfig,
    RatePolicyDomain,
)
from apps.shared.api_connector.schemas import ApiConnectorResponse, ApiOperationResponse, ApiRatePolicySchema
from apps.shared.db.models import ApiConnector, ApiOperationIndex
from apps.shared.utils.field_cipher import AUTH_CONFIG_SENSITIVE_FIELDS, FieldCipher


def auth_config_to_dict(auth_config: Any) -> dict[str, Any]:
    """Normalize request/domain auth_config to a JSON-serializable dict."""
    if not auth_config:
        return {}
    if isinstance(auth_config, dict):
        return auth_config
    if isinstance(auth_config, BaseModel):
        return auth_config.model_dump()
    if dataclasses.is_dataclass(auth_config) and not isinstance(auth_config, type):
        return dataclasses.asdict(auth_config)
    raise TypeError(f"Unsupported auth_config type: {type(auth_config).__name__}")


def _dict_to_auth_config(auth_type: str, auth_dict: dict[str, Any]):
    """Convert raw dict to typed domain auth config dataclass.

    Args:
        auth_type: The auth type string (api_key, bearer, basic, custom, none)
        auth_dict: Decrypted auth config dict from database

    Returns:
        Typed AuthConfig dataclass instance
    """
    if not auth_dict:
        return NoAuthConfig()

    match auth_type:
        case "api_key":
            return ApiKeyAuthConfig(
                key_name=auth_dict.get("key_name", "X-API-Key"),
                key_value=auth_dict.get("key_value"),
                api_key=auth_dict.get("api_key"),
            )
        case "bearer":
            return BearerAuthConfig(
                token=auth_dict.get("token"),
                access_token=auth_dict.get("access_token"),
            )
        case "basic":
            return BasicAuthConfig(
                username=auth_dict.get("username"),
                password=auth_dict.get("password"),
            )
        case "custom":
            return CustomAuthConfig(
                login_endpoint=auth_dict.get("login_endpoint", ""),
                login_method=auth_dict.get("login_method", "POST"),
                login_payload_template=auth_dict.get("login_payload_template", {}),
                token_extraction=auth_dict.get("token_extraction", {}),
                request_headers=auth_dict.get("request_headers", {}),
                extra_config=auth_dict.get("extra_config", {}),
            )
        case _:
            return NoAuthConfig()


def connector_entity_to_domain(connector: ApiConnector, cipher: FieldCipher | None = None) -> ApiConnectorDomain:
    """Convert DB entity to domain model.

    Args:
        connector: DB entity
        cipher: Optional FieldCipher for auto-decrypting auth_config. If None, auth_config remains encrypted.
    """
    owner_name = (
        connector.owner_user.username
        if connector.owner_user
        else "已删除用户"
        if connector.owner_id is not None
        else None
    )

    # Auto-decrypt auth_config if cipher is provided, then convert to domain dataclass
    raw_auth_config = connector.auth_config or {}
    if cipher and raw_auth_config:
        decrypted_dict = cipher.decrypt_dict(raw_auth_config, sensitive_fields=AUTH_CONFIG_SENSITIVE_FIELDS)
    else:
        decrypted_dict = raw_auth_config

    auth_config = _dict_to_auth_config(connector.auth_type, decrypted_dict)

    return ApiConnectorDomain(
        id=connector.id,
        tenant_id=connector.tenant_id,
        owner_id=connector.owner_id,
        owner_name=owner_name,
        name=connector.name,
        description=connector.description,
        base_url=connector.base_url,
        auth_type=connector.auth_type,
        auth_config=auth_config,
        rate_policy=RatePolicyDomain.from_raw(connector.rate_policy),
        schema_source_type=connector.schema_source_type,
        schema_source_url=connector.schema_source_url,
        schema_metadata=connector.schema_metadata or {},
        schema_last_synced_at=connector.schema_last_synced_at,
        status=connector.status,
        created_at=connector.created_at,
        updated_at=connector.updated_at,
    )


def operation_entity_to_domain(
    operation: ApiOperationIndex,
    resource_index: Any | None = None,
) -> ApiOperationDomain:
    return ApiOperationDomain(
        id=operation.id,
        connector_id=operation.connector_id,
        operation_uid=operation.operation_uid,
        method=operation.method,
        path_template=operation.path_template,
        operation_id=operation.operation_id,
        summary=operation.summary,
        description=operation.description,
        tags=operation.tags or [],
        request_schema=operation.request_schema,
        response_schema=operation.response_schema,
        auth_requirement=operation.auth_requirement,
        risk_level=operation.risk_level,
        source=operation.source,
        upstream_key=operation.upstream_key,
        content_hash=operation.content_hash,
        status=operation.status,
        owner_id=operation.owner_id,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
        last_vector_synced_at=resource_index.vector_synced_at if resource_index else None,
        last_vector_sync_error=resource_index.vector_sync_error if resource_index else None,
        last_vector_sync_failed_at=resource_index.vector_sync_error_at if resource_index else None,
    )


def connector_domain_to_response(connector: ApiConnectorDomain) -> ApiConnectorResponse:
    """Convert domain model to response DTO with masked auth_config.

    The auth_config in the domain model is a typed dataclass (already decrypted).
    This function converts it to dict and masks sensitive fields before creating the response DTO.

    Args:
        connector: Domain model with decrypted auth_config dataclass

    Returns:
        Response DTO with masked auth_config
    """
    auth_config_dict = auth_config_to_dict(connector.auth_config)

    masked_auth_config = FieldCipher.mask_dict(auth_config_dict, sensitive_fields=AUTH_CONFIG_SENSITIVE_FIELDS)

    return ApiConnectorResponse(
        id=connector.id,
        tenant_id=connector.tenant_id,
        owner_id=connector.owner_id,
        owner_name=connector.owner_name,
        name=connector.name,
        description=connector.description,
        base_url=connector.base_url,
        auth_type=connector.auth_type,
        auth_config_masked=masked_auth_config,
        rate_policy=ApiRatePolicySchema.from_domain(connector.rate_policy),
        schema_source_type=connector.schema_source_type,
        schema_source_url=connector.schema_source_url,
        schema_metadata=connector.schema_metadata,
        schema_last_synced_at=connector.schema_last_synced_at,
        status=connector.status,
        created_at=connector.created_at,
        updated_at=connector.updated_at,
    )


def operation_domain_to_response(operation: ApiOperationDomain) -> ApiOperationResponse:
    return ApiOperationResponse(
        id=operation.id,
        connector_id=operation.connector_id,
        operation_uid=operation.operation_uid,
        method=operation.method,
        path_template=operation.path_template,
        operation_id=operation.operation_id,
        summary=operation.summary,
        description=operation.description,
        tags=operation.tags,
        request_schema=operation.request_schema,
        response_schema=operation.response_schema,
        auth_requirement=operation.auth_requirement,
        risk_level=operation.risk_level,
        source=operation.source,
        upstream_key=operation.upstream_key,
        status=operation.status,
        owner_id=operation.owner_id,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
        last_vector_synced_at=operation.last_vector_synced_at,
        last_vector_sync_error=operation.last_vector_sync_error,
        last_vector_sync_failed_at=operation.last_vector_sync_failed_at,
    )
