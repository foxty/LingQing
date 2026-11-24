"""Encrypted, short-lived OAuth authorization state for API connector BYOT."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apps.shared.core.exceptions import ValidationError
from apps.shared.infra.oauth.pkce import code_challenge
from apps.shared.utils.field_cipher import FieldCipher

STATE_TTL_MINUTES = 10


@dataclass(frozen=True)
class OAuthState:
    tenant_id: int
    user_id: int
    connector_id: int
    redirect_uri: str
    code_verifier: str
    expires_at: datetime


class OAuthStateCodec:
    """API-connector-scoped state; not a generic OAuth primitive."""

    def __init__(self, cipher: FieldCipher | None = None) -> None:
        self._cipher = cipher or FieldCipher()

    def issue(
        self,
        *,
        tenant_id: int,
        user_id: int,
        connector_id: int,
        redirect_uri: str,
    ) -> tuple[str, str]:
        verifier = secrets.token_urlsafe(64)
        expires_at = datetime.now(UTC) + timedelta(minutes=STATE_TTL_MINUTES)
        payload = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "connector_id": connector_id,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
            "expires_at": expires_at.isoformat(),
        }
        return self._cipher.encrypt(json.dumps(payload, separators=(",", ":"))), verifier

    def decode(self, state: str) -> OAuthState:
        try:
            payload = json.loads(self._cipher.decrypt(state))
            decoded = OAuthState(
                tenant_id=int(payload["tenant_id"]),
                user_id=int(payload["user_id"]),
                connector_id=int(payload["connector_id"]),
                redirect_uri=str(payload["redirect_uri"]),
                code_verifier=str(payload["code_verifier"]),
                expires_at=datetime.fromisoformat(payload["expires_at"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValidationError("Invalid OAuth state") from exc
        if decoded.expires_at.astimezone(UTC) <= datetime.now(UTC):
            raise ValidationError("OAuth state expired; start the connection again")
        return decoded

    @staticmethod
    def code_challenge(verifier: str) -> str:
        return code_challenge(verifier)
