"""Declarative secret policies for JSON blobs (encrypt, GET, merge, BYOT strip).

Policy *instances* live in owning bounded contexts (data_source, api_connector, credentials).
This module only defines the generic shape — no product config layout here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.shared.utils.sensitive_redaction import SecretLeafSpec


@dataclass(frozen=True)
class TemplateStripPolicy:
    """Remove shared login/template fields before overlaying per-user secrets."""

    top_level_keys: frozenset[str]
    retain_subtrees: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class JsonSecretPolicy:
    """One persisted JSON document (config, auth_config, secrets_enc)."""

    root: str
    encrypt_leaves: frozenset[str]
    get_specs: tuple[SecretLeafSpec, ...]
    merge_preserve_leaves: frozenset[str]
    template_strip: TemplateStripPolicy | None = None

    @property
    def user_mode_strip_top_level(self) -> frozenset[str]:
        if self.template_strip is None:
            return frozenset()
        return self.template_strip.top_level_keys