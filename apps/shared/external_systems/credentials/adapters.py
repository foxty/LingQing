"""BYOT connection GET: redact ``secrets`` blob and ``masked_fields`` (approach A)."""

from __future__ import annotations

from typing import Any

from apps.shared.external_systems.credentials.user_secrets_policy import USER_BINDING_POLICY
from apps.shared.utils.secret_engines import redact_for_get
from apps.shared.utils.secret_wire import mask_secret_for_display
from apps.shared.utils.sensitive_redaction import config_has_secret_value


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
    redacted, masked_fields = redact_for_get(
        normalized,
        USER_BINDING_POLICY,
        mask_value=_mask_secret_for_api_display,
    )
    secrets = {key: value for key, value in redacted.items() if isinstance(value, str)}
    return secrets, masked_fields
