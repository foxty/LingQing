"""Unit tests for document sync domain helpers."""

from __future__ import annotations

import pytest

from apps.shared.core.exceptions import ValidationError
from apps.shared.document.sync_domain import (
    GoogleDriveProviderConfig,
    provider_label,
    require_provider_enabled,
)
from apps.shared.document.sync_types import DocumentSourceProviderKey


def test_google_drive_provider_config_from_dict():
    config = GoogleDriveProviderConfig.from_dict(
        {"client_id": " cid ", "client_secret": " secret "},
    )
    assert config.client_id == "cid"
    assert config.client_secret == "secret"
    assert config.is_configured is True


def test_google_drive_provider_config_require_configured_raises():
    config = GoogleDriveProviderConfig.from_dict({"client_id": "", "client_secret": ""})
    with pytest.raises(ValidationError) as exc:
        config.require_configured(provider_key=DocumentSourceProviderKey.GOOGLE_DRIVE)
    assert exc.value.details["code"] == "SOURCE_NOT_CONFIGURED"


def test_provider_label_known_key():
    assert provider_label(DocumentSourceProviderKey.GOOGLE_DRIVE) == "Google Drive"


def test_provider_label_unknown_key_title_cases():
    assert provider_label("box_drive") == "Box Drive"


def test_require_provider_enabled_raises_when_disabled():
    with pytest.raises(ValidationError) as exc:
        require_provider_enabled(
            provider_key=DocumentSourceProviderKey.GOOGLE_DRIVE,
            enabled=False,
        )
    assert exc.value.details["code"] == "SOURCE_DISABLED"
