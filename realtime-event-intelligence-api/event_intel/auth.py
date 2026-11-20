"""Bearer-token auth with scopes and expiry, OAuth2/OIDC style.

Tokens are opaque random strings minted with a set of scopes and a
time-to-live. Validation checks the token exists, has not expired, and
carries the required scope. This is a local stand-in for an identity
provider (OAuth, Okta, or similar); it issues and checks tokens only.
"""

from __future__ import annotations

import secrets
import time

ALL_SCOPES = frozenset({"events:write", "alerts:read"})


class AuthError(Exception):
    """Raised when a token is missing, expired, or lacks a scope."""


class TokenStore:
    def __init__(self):
        # token -> {"scopes": set[str], "expires_at": float}
        self._tokens: dict[str, dict] = {}

    def mint_token(self, scopes, ttl_seconds: int = 3600) -> str:
        unknown = set(scopes) - ALL_SCOPES
        if unknown:
            raise ValueError(f"unknown scopes: {sorted(unknown)}")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        token = secrets.token_urlsafe(32)
        self._tokens[token] = {
            "scopes": set(scopes),
            "expires_at": time.time() + ttl_seconds,
        }
        return token

    def validate(self, token: str | None, required_scope: str) -> None:
        """Raise AuthError unless the token is live and has the scope."""
        if not token:
            raise AuthError("missing bearer token")
        entry = self._tokens.get(token)
        if entry is None:
            raise AuthError("unknown bearer token")
        if time.time() >= entry["expires_at"]:
            raise AuthError("bearer token expired")
        if required_scope not in entry["scopes"]:
            raise AuthError(f"token lacks scope {required_scope}")


def bearer_from_header(header: str | None) -> str | None:
    """Extract the token from an `Authorization: Bearer <token>` header."""
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token
