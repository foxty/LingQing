"""Domain config models for external document source providers."""

from __future__ import annotations

from dataclasses import dataclass

from apps.shared.core.exceptions import ValidationError
from apps.shared.document.sync_types import DocumentSourceProviderKey


@dataclass(frozen=True)
class GoogleDriveProviderConfig:
    client_id: str
    client_secret: str

    @classmethod
    def from_dict(cls, raw: dict) -> GoogleDriveProviderConfig:
        return cls(
            client_id=(raw.get("client_id") or "").strip(),
            client_secret=(raw.get("client_secret") or "").strip(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def require_configured(self, *, provider_key: str) -> None:
        if self.is_configured:
            return
        label = provider_label(provider_key)
        raise ValidationError(
            f"{label} OAuth is not configured for this tenant",
            {"code": "SOURCE_NOT_CONFIGURED", "provider": provider_key},
        )


def provider_label(provider_key: str) -> str:
    labels = {
        DocumentSourceProviderKey.GOOGLE_DRIVE.value: "Google Drive",
    }
    return labels.get(provider_key, provider_key.replace("_", " ").title())


def require_provider_enabled(*, provider_key: str, enabled: bool) -> None:
    if enabled:
        return
    raise ValidationError(
        f"{provider_label(provider_key)} source is not enabled for this tenant",
        {"code": "SOURCE_DISABLED", "provider": provider_key},
    )
