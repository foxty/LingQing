"""BYOT connection GET: redact ``secrets`` blob and ``masked_fields`` (approach A)."""

from __future__ import annotations

from typing import Any

from apps.shared.external_systems.credentials.sensitive_config import USER_INTEGRATION_GET_SECRET_SPECS
from apps.shared.utils.secret_wire import mask_secret_for_display
from apps.shared.utils.sensitive_redaction import (
    config_has_secret_value,
    redact_secret_leaves_for_get,
)


def _mask_secret_for_api_display(raw: Any) -> str | None:
    if not config_has_secret_value(raw):
        return None
    masked = mask_secret_for_display(str(raw))
    return masked or None


def redact_user_integration_secrets_for_api(
    decrypted: dict[str, Any] | None,
) -> tuple[dict[str, str], list[str]]:
    """Build GET ``secrets`` + root-relative ``masked_fields`` paths."""
    if not decrypted:
        return {}, []
    normalized = {
        key: value
        for key, value in decrypted.items()
        if isinstance(value, str) and value.strip()
    }
    redacted, masked_fields = redact_secret_leaves_for_get(
        normalized,
        USER_INTEGRATION_GET_SECRET_SPECS,
        mask_value=_mask_secret_for_api_display,
    )
    secrets = {key: value for key, value in redacted.items() if isinstance(value, str)}
    return secrets, masked_fields
