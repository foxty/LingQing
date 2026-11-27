"""Per-user OAuth (U2M) configuration on data sources (Databricks SQL)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from apps.shared.core.exceptions import ValidationError
from apps.shared.domain.value_objects import DataSourceType
from apps.shared.external_systems.credentials.domain import (
    AUTH_TYPE_OAUTH2,
    USER_INTEGRATION_AUTH_PAT,
    UserCredentialAuthTypeStr,
)
from apps.shared.external_systems.domain.types import CREDENTIAL_MODE_USER
from apps.shared.infra.oauth import TOKEN_AUTH_METHOD_CLIENT_SECRET_POST
from apps.shared.utils.field_cipher import FieldCipher

USER_CREDENTIAL_AUTH_TYPE_KEY = "user_credential_auth_type"
USER_OAUTH_CONFIG_KEY = "user_oauth"

# Config values (pat | oauth2); same literals as credentials domain, kept as aliases for importers.
USER_CREDENTIAL_AUTH_PAT = USER_INTEGRATION_AUTH_PAT
USER_CREDENTIAL_AUTH_OAUTH2 = AUTH_TYPE_OAUTH2

USER_OAUTH_SENSITIVE_FIELDS: frozenset[str] = frozenset({"client_secret"})

DATABRICKS_OAUTH_SCOPES_REQUIRED_MSG = (
    "Databricks OAuth requires at least one authorize scope matching your OAuth app "
    "(for example sql:read:restricted-query, sql:restricted-query, and offline_access)."
)


def _authorize_scopes_from_block(block: Mapping[str, Any] | dict[str, Any]) -> list[str]:
    scopes = block.get("scopes")
    if isinstance(scopes, (list, tuple)):
        return [str(item).strip() for item in scopes if str(item).strip()]
    return []


def validate_databricks_oauth_authorize_scopes(scope_list: list[str]) -> None:
    """Databricks OIDC rejects authorize requests with no ``scope`` parameter."""
    if not scope_list:
        raise ValidationError(DATABRICKS_OAUTH_SCOPES_REQUIRED_MSG)

def user_credential_auth_type_from_config(config: dict[str, Any] | None) -> UserCredentialAuthTypeStr:
    """Return ``pat`` or ``oauth2`` from persisted data-source config (default ``pat``)."""
    raw = (config or {}).get(USER_CREDENTIAL_AUTH_TYPE_KEY)
    if isinstance(raw, str) and raw.strip() == USER_CREDENTIAL_AUTH_OAUTH2:
        return USER_CREDENTIAL_AUTH_OAUTH2
    return USER_CREDENTIAL_AUTH_PAT


def databricks_oidc_urls(host: str) -> tuple[str, str]:
    """Derive workspace OIDC authorize/token URLs from hostname."""
    normalized = (host or "").strip()
    if not normalized:
        raise ValidationError("Databricks host is required for OAuth URLs")
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"
    base = normalized.rstrip("/")
    return f"{base}/oidc/v1/authorize", f"{base}/oidc/v1/token"


def validate_databricks_user_oauth_settings(
    *,
    data_source_type: str,
    credential_mode: str,
    managed: bool,
    config: dict[str, Any] | None,
) -> None:
    """Validate admin config when Databricks uses per-user OAuth2."""
    if user_credential_auth_type_from_config(config) != USER_CREDENTIAL_AUTH_OAUTH2:
        return
    if data_source_type != DataSourceType.DATABRICKS:
        raise ValidationError("OAuth2 user credentials are only supported for Databricks data sources")
    if managed:
        raise ValidationError("Managed data sources cannot use per-user OAuth2")
    if credential_mode != CREDENTIAL_MODE_USER:
        raise ValidationError("OAuth2 user credentials require credential_mode=user")
    block = (config or {}).get(USER_OAUTH_CONFIG_KEY)
    if not isinstance(block, dict):
        raise ValidationError(f"config.{USER_OAUTH_CONFIG_KEY} is required for OAuth2 user credentials")
    host = ((config or {}).get("host") or "").strip()
    if not host:
        raise ValidationError("Databricks host is required for OAuth2 user credentials")
    client_id = (block.get("client_id") or "").strip()
    if not client_id:
        raise ValidationError("OAuth client_id is required")
    redirect_uri = (block.get("redirect_uri") or "").strip()
    if not redirect_uri:
        raise ValidationError("OAuth redirect_uri is required")
    authorize = (block.get("authorize_url") or "").strip()
    token_url = (block.get("token_url") or "").strip()
    if not authorize or not token_url:
        raise ValidationError("OAuth authorize_url and token_url are required in user_oauth config")
    validate_databricks_oauth_authorize_scopes(_authorize_scopes_from_block(block))


def decrypt_user_oauth_block(
    config: dict[str, Any] | None,
    *,
    cipher: FieldCipher | None = None,
) -> dict[str, Any]:
    block = (config or {}).get(USER_OAUTH_CONFIG_KEY)
    if not isinstance(block, dict) or not block:
        return {}
    cipher = cipher or FieldCipher()
    return cipher.decrypt_dict(block, sensitive_fields=USER_OAUTH_SENSITIVE_FIELDS)


def oauth_client_fields_from_data_source_config(
    config: dict[str, Any] | None,
    *,
    cipher: FieldCipher | None = None,
) -> dict[str, Any]:
    """Parse stored ``user_oauth`` into OAuth2 client fields (no api_connector imports)."""
    raw = decrypt_user_oauth_block(config, cipher=cipher)
    if not raw:
        raise ValidationError("Data source is not configured for user OAuth2")
    authorize = (raw.get("authorize_url") or "").strip()
    token_url = (raw.get("token_url") or "").strip()
    if not authorize or not token_url:
        raise ValidationError("OAuth authorize_url and token_url are required")
    scope_param = (raw.get("scope_param") or "scope").strip() or "scope"
    token_auth_method = raw.get("token_auth_method") or TOKEN_AUTH_METHOD_CLIENT_SECRET_POST
    redirect_uri = raw.get("redirect_uri")
    redirect_uri = redirect_uri.strip() if isinstance(redirect_uri, str) else ""
    if not redirect_uri:
        raise ValidationError("OAuth redirect_uri is required")
    scope_list = _authorize_scopes_from_block(raw)
    validate_databricks_oauth_authorize_scopes(scope_list)
    token_response_path = raw.get("token_response_path")
    if isinstance(token_response_path, str) and not token_response_path.strip():
        token_response_path = None
    return {
        "authorize_url": authorize,
        "token_url": token_url,
        "client_id": str(raw.get("client_id") or "").strip(),
        "client_secret": raw.get("client_secret") or None,
        "scopes": scope_list,
        "scope_param": scope_param,
        "redirect_uri": redirect_uri,
        "token_auth_method": token_auth_method,
        "token_response_path": token_response_path,
    }


def oauth_token_refresh_template(
    config: dict[str, Any] | None,
    *,
    cipher: FieldCipher | None = None,
) -> dict[str, Any]:
    """Administrator-controlled token endpoint settings for refresh (resolver)."""
    fields = oauth_client_fields_from_data_source_config(config, cipher=cipher)
    return {
        "token_url": fields["token_url"],
        "client_id": fields["client_id"],
        "client_secret": fields.get("client_secret"),
        "token_auth_method": fields.get("token_auth_method"),
        "token_response_path": fields.get("token_response_path"),
    }


def merge_user_oauth_into_config(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
    *,
    cipher: FieldCipher | None = None,
) -> dict[str, Any]:
    """Merge PATCH config while preserving stored secrets when omitted (plaintext in/out)."""
    from apps.shared.external_systems.data_source.config_secrets_policy import (
        DATA_SOURCE_CONFIG_POLICY,
        decrypt_data_source_config_from_storage,
    )
    from apps.shared.utils.secret_engines import merge_config

    cipher = cipher or FieldCipher()
    base = decrypt_data_source_config_from_storage(existing, cipher=cipher) if existing else {}
    return merge_config(base, incoming, DATA_SOURCE_CONFIG_POLICY)