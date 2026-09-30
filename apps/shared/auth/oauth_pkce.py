"""Shared OAuth PKCE helpers for OIDC and document source connect flows."""

from __future__ import annotations

import base64
import hashlib
import secrets


def generate_pkce() -> tuple[str, str, str]:
    """Return (state, code_verifier, code_challenge) for an OAuth PKCE flow."""
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return state, code_verifier, code_challenge


def generate_nonce() -> str:
    return secrets.token_urlsafe(32)
