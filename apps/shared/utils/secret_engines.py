"""Apply ``JsonSecretPolicy`` to encrypt, redact, merge, and strip (thin wrappers)."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from apps.shared.utils.field_cipher import FieldCipher
from apps.shared.utils.secret_merge import merge_dict_preserve_secrets
from apps.shared.utils.secret_policy import JsonSecretPolicy, TemplateStripPolicy
from apps.shared.utils.sensitive_redaction import redact_secret_leaves_for_get


def encrypt_config(data: dict[str, Any], policy: JsonSecretPolicy, *, cipher: FieldCipher | None = None) -> dict[str, Any]:
    cipher = cipher or FieldCipher()
    return cipher.encrypt_dict(data, sensitive_fields=set(policy.encrypt_leaves))


def decrypt_config(
    data: dict[str, Any],
    policy: JsonSecretPolicy,
    *,
    cipher: FieldCipher | None = None,
) -> dict[str, Any]:
    cipher = cipher or FieldCipher()
    return cipher.decrypt_dict(data, sensitive_fields=set(policy.encrypt_leaves))


def redact_for_get(
    data: dict[str, Any],
    policy: JsonSecretPolicy,
    *,
    mask_value: Callable[[Any], str | None],
) -> tuple[dict[str, Any], list[str]]:
    return redact_secret_leaves_for_get(data, policy.get_specs, mask_value=mask_value)


def merge_config(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
    policy: JsonSecretPolicy,
) -> dict[str, Any]:
    return merge_dict_preserve_secrets(
        existing,
        incoming,
        sensitive_keys=set(policy.merge_preserve_leaves),
    )


def strip_template(data: dict[str, Any], template: TemplateStripPolicy) -> dict[str, Any]:
    """Top-level strip; optional retain entire subtrees by first path segment."""
    cleaned = deepcopy(data)
    retain_roots = {path[0] for path in template.retain_subtrees if path}
    for key in list(cleaned.keys()):
        if key in retain_roots:
            continue
        if key in template.top_level_keys:
            del cleaned[key]
    return cleaned