"""OAuth PKCE helpers shared by SSO, document sync, and integration connect flows."""

from __future__ import annotations

import base64
import hashlib
import secrets


def generate_pkce() -> tuple[str, str, str]:
    """Return (state, code_verifier, code_challenge) for an OAuth PKCE flow."""
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(48)
    return state, code_verifier, code_challenge(code_verifier)


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_nonce() -> str:
    return secrets.token_urlsafe(32)
