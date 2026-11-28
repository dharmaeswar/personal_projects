"""Delegated credentials: HMAC-signed agentic tokens with replay protection.

A token is a signed statement that a user delegated limited authority to
one agent: which scopes it may use, which merchants, a spend cap, and an
expiry.  The signature is HMAC-SHA256 over a canonical payload, so any
tampering (a raised cap, an added scope, a swapped merchant) fails
verification.  Tokens are single-use per idempotency key: the replay guard
refuses a token/key pair it has already seen, so a captured token cannot
be replayed to double-charge.

The signing secret is passed in by the caller.  In this demo it is a
constant labelled DEMO — a real deployment would hold it in a vault/KMS
and never ship it in code.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone


class TokenError(ValueError):
    """Raised when a delegated token is malformed, forged, or expired."""


@dataclass(frozen=True)
class DelegatedToken:
    token_id: str
    agent_id: str
    user_id: str
    scopes: frozenset
    merchant_allowlist: frozenset
    max_amount_cents: int
    expires_at: datetime

    def allows(self, scope: str, merchant_id: str, amount_cents: int,
               now: datetime | None = None) -> list[str]:
        """Violations for using this token for one action; empty = allowed."""
        now = now or datetime.now(timezone.utc)
        problems: list[str] = []
        if scope not in self.scopes:
            problems.append(f"scope {scope!r} is not granted by the token")
        if self.merchant_allowlist and merchant_id not in self.merchant_allowlist:
            problems.append(f"merchant {merchant_id!r} is not allowlisted")
        if amount_cents > self.max_amount_cents:
            problems.append("amount exceeds the token spend cap")
        if now >= self.expires_at:
            problems.append("token has expired")
        return problems


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(*, agent_id: str, user_id: str, scopes, merchant_allowlist=(),
                max_amount_cents: int, expires_at: datetime,
                secret: bytes, token_id: str | None = None) -> str:
    """Mint a signed delegated token. Returns the compact token string."""
    payload = {
        "token_id": token_id or f"tok_{secrets.token_hex(8)}",
        "agent_id": agent_id,
        "user_id": user_id,
        "scopes": sorted(scopes),
        "merchants": sorted(merchant_allowlist),
        "max_amount_cents": max_amount_cents,
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
    }
    body = _b64(json.dumps(payload, sort_keys=True).encode())
    sig = hmac.new(secret, body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(sig)}"


def verify_token(token_str: str, secret: bytes,
                 now: datetime | None = None) -> DelegatedToken:
    """Verify the signature and expiry; return the decoded token."""
    now = now or datetime.now(timezone.utc)
    try:
        body, sig = token_str.rsplit(".", 1)
        expected = hmac.new(secret, body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(sig)):
            raise TokenError("token signature does not match")
        payload = json.loads(_unb64(body))
        token = DelegatedToken(
            token_id=payload["token_id"],
            agent_id=payload["agent_id"],
            user_id=payload["user_id"],
            scopes=frozenset(payload["scopes"]),
            merchant_allowlist=frozenset(payload["merchants"]),
            max_amount_cents=int(payload["max_amount_cents"]),
            expires_at=datetime.fromisoformat(payload["expires_at"]),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise TokenError(f"malformed token: {exc}") from exc
    if now >= token.expires_at:
        raise TokenError("token has expired")
    return token


class ReplayGuard:
    """Refuses a (token_id, idempotency_key) pair it has already seen."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def check_and_mark(self, token_id: str, idempotency_key: str) -> bool:
        """True if this is the first use; False if it is a replay."""
        pair = (token_id, idempotency_key)
        if pair in self._seen:
            return False
        self._seen.add(pair)
        return True
