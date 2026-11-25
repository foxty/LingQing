"""OAuth 2.0 authorization URL builder (RFC 6749 + PKCE S256)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from apps.shared.core.exceptions import ValidationError

PROTECTED_AUTHORIZE_PARAMS = frozenset(
    {
        "response_type",
        "client_id",
        "redirect_uri",
        "state",
        "code_challenge",
        "code_challenge_method",
    }
)


def build_authorize_url(
    authorize_url: str,
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scopes: Sequence[str] | None = None,
    scope_param: str = "scope",
    extra_params: Mapping[str, str] | None = None,
) -> str:
    """Append standard Authorization Code + S256 PKCE query parameters to ``authorize_url``."""
    if scope_param in PROTECTED_AUTHORIZE_PARAMS:
        raise ValidationError(f"OAuth scope parameter cannot be '{scope_param}'")
    protected_params = PROTECTED_AUTHORIZE_PARAMS | {scope_param}
    collisions = protected_params.intersection(extra_params or ())
    if collisions:
        names = ", ".join(sorted(collisions))
        raise ValidationError(f"OAuth extra authorize parameters cannot override: {names}")

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if scopes:
        params[scope_param] = " ".join(scopes)
    if extra_params:
        params.update(extra_params)

    parts = urlsplit(authorize_url)
    existing_query = [
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key not in protected_params
    ]
    query = [*existing_query, *params.items()]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
