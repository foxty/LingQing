"""BYOT shared-template strip helpers (no imports from connector/data_source packages)."""

from __future__ import annotations

from typing import Any

from apps.shared.external_systems.integration_secret_keys import INTEGRATION_SECRET_LEAF_KEYS
from apps.shared.utils.field_cipher import strip_sensitive_fields
from apps.shared.utils.secret_engines import strip_template
from apps.shared.utils.secret_policy import TemplateStripPolicy

OAUTH2_ACTOR_TOKEN_STRIP_KEYS: frozenset[str] = frozenset({"token", "access_token", "refresh_token"})

CONNECTOR_AUTH_TEMPLATE_STRIP = TemplateStripPolicy(top_level_keys=INTEGRATION_SECRET_LEAF_KEYS)


def strip_connector_auth_user_mode_template(
    auth_config: dict[str, Any],
    *,
    auth_type: str,
) -> dict[str, Any]:
    """Remove shared connector auth before overlaying per-user secrets."""
    if auth_type == "oauth2":
        return strip_sensitive_fields(auth_config, sensitive_keys=OAUTH2_ACTOR_TOKEN_STRIP_KEYS)
    return strip_template(auth_config, CONNECTOR_AUTH_TEMPLATE_STRIP)