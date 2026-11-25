"""Encrypted, short-lived OAuth authorization state for user-scoped integrations."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from apps.shared.core.exceptions import ValidationError
from apps.shared.domain.types import RESOURCE_TYPE_API_CONNECTOR
from apps.shared.infra.oauth.pkce import code_challenge
from apps.shared.utils.field_cipher import FieldCipher

STATE_TTL_MINUTES = 10


@dataclass(frozen=True)
class OAuthState:
    tenant_id: int
    user_id: int
    resource_type: str
    resource_id: int
    redirect_uri: str
    code_verifier: str
    expires_at: datetime


class OAuthStateCodec:
    """Resource-typed encrypted state for user-scoped integration OAuth flows."""

    def __init__(self, cipher: FieldCipher | None = None) -> None:
        self._cipher = cipher or FieldCipher()

    def issue(
        self,
        *,
        tenant_id: int,
        user_id: int,
        redirect_uri: str,
        resource_id: int,
        resource_type: str = RESOURCE_TYPE_API_CONNECTOR,
    ) -> tuple[str, str]:
        normalized_type = resource_type.strip()
        if not normalized_type:
            raise ValidationError("OAuth state requires resource_type")

        verifier = secrets.token_urlsafe(64)
        expires_at = datetime.now(UTC) + timedelta(minutes=STATE_TTL_MINUTES)
        payload = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "resource_type": normalized_type,
            "resource_id": resource_id,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
            "expires_at": expires_at.isoformat(),
        }
        return self._cipher.encrypt(json.dumps(payload, separators=(",", ":"))), verifier

    def decode(self, state: str) -> OAuthState:
        if not state.startswith("enc:"):
            raise ValidationError("Invalid OAuth state")
        try:
            payload = json.loads(self._cipher.decrypt(state))
            if "resource_type" in payload and "resource_id" in payload:
                resource_type = str(payload["resource_type"]).strip()
                resource_id = int(payload["resource_id"])
            else:
                # Legacy payloads issued before resource_type generalization.
                resource_type = RESOURCE_TYPE_API_CONNECTOR
                resource_id = int(payload["connector_id"])
            if not resource_type:
                raise ValueError("empty resource_type")
            decoded = OAuthState(
                tenant_id=int(payload["tenant_id"]),
                user_id=int(payload["user_id"]),
                resource_type=resource_type,
                resource_id=resource_id,
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
